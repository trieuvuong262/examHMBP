from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_SAN_PHAM
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_san_pham.choices import (
    PRODUCT_TYPE_CHOICES,
    PRODUCT_TYPE_HANG_HOA,
    PRODUCT_TYPE_LABELS,
    SYNC_SOURCE_MANUAL,
)
from kho_san_pham.forms import ProductForm
from kho_san_pham.models import Product
from kho_san_pham.product_list_columns import PRODUCT_LIST_SORT_FIELDS
from kho_san_pham.services.stock import StockMovementError, set_catalog_qty
from kho_san_pham.services.product_import_export import (
    ProductImportError,
    export_products_xlsx,
    import_products_from_excel,
    sample_template_xlsx,
)
from kho_san_pham.services.accounting_import import import_accounting_from_invoice_excel
from kho_san_pham.services.style_groups import format_style_group, group_products_by_style
from kho_san_pham.services.sync_from_kiotviet import sync_thanh_pham_from_kiotviet
from kho_san_pham.view_utils import nav_context, perm_context

STATUS_CHOICES = (
    ('all', 'Tất cả'),
    ('active', 'Đang dùng'),
    ('inactive', 'Ngừng dùng'),
)


def _list_status(request) -> str:
    status = (request.GET.get('status') or 'active').strip().lower()
    if status not in {k for k, _ in STATUS_CHOICES}:
        return 'active'
    return status


def _list_type(request) -> str:
    value = (request.GET.get('type') or '').strip()
    if value in PRODUCT_TYPE_LABELS:
        return value
    return ''


def _list_sort(request):
    sort_key = (request.GET.get('sort') or 'code').strip()
    sort_dir = (request.GET.get('dir') or 'asc').strip().lower()
    if sort_key not in PRODUCT_LIST_SORT_FIELDS:
        sort_key = 'code'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'
    return sort_key, sort_dir


def _product_list_qs(request):
    search_query = get_search_query(request)
    status = _list_status(request)
    product_type = _list_type(request)
    qs = Product.objects.all()
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    if product_type:
        qs = qs.filter(product_type=product_type)
    if search_query:
        qs = qs.filter(
            Q(code__icontains=search_query)
            | Q(style_code__icontains=search_query)
            | Q(color_code__icontains=search_query)
            | Q(color_label__icontains=search_query)
            | Q(size_label__icontains=search_query)
            | Q(accounting_code__icontains=search_query)
            | Q(kiotviet_code__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(bar_code__icontains=search_query)
            | Q(category_name__icontains=search_query)
        )
    sort_key, sort_dir = _list_sort(request)
    order = PRODUCT_LIST_SORT_FIELDS[sort_key]
    if sort_dir == 'desc':
        order = f'-{order}'
    qs = qs.order_by(order, 'code')
    return qs, search_query, status, product_type, sort_key, sort_dir


def _apply_catalog_qty(product, form, *, user) -> None:
    qty = form.cleaned_data.get('qty_on_hand')
    if qty is None:
        return
    set_catalog_qty(product, qty, user=user)


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def hub_redirect(request):
    return redirect('kho_san_pham:product_list')


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def product_list(request):
    qs, search_query, status, product_type, sort_key, sort_dir = _product_list_qs(request)
    # Gom theo Style trước khi phân trang (giống Bán hàng – Hàng hoá)
    products = list(qs[:2000])
    groups = [format_style_group(g) for g in group_products_by_style(products)]
    page_obj, query_string = paginate_queryset(request, groups, per_page=40)

    # Đánh dấu nhóm đã có hồ sơ thiết kế (theo mã SX / style)
    from django.db.models import Q
    from san_xuat.models import ProductTechDoc

    candidate_codes: set[str] = set()
    for item in page_obj.object_list:
        style = (item.get('style_code') or '').strip()
        if style and style != '—':
            candidate_codes.add(style)
        for v in item.get('variants') or []:
            code = (getattr(v, 'code', None) or '').strip()
            if code:
                candidate_codes.add(code)
    doc_codes: set[str] = set()
    if candidate_codes:
        q_docs = Q()
        for c in candidate_codes:
            q_docs |= Q(product_code__iexact=c)
        doc_codes = {
            (code or '').casefold()
            for code in ProductTechDoc.objects.filter(q_docs).values_list('product_code', flat=True)
        }
    for item in page_obj.object_list:
        style = (item.get('style_code') or '').strip()
        hit = bool(style and style != '—' and style.casefold() in doc_codes)
        if not hit:
            for v in item.get('variants') or []:
                code = (getattr(v, 'code', None) or '').strip()
                if code and code.casefold() in doc_codes:
                    hit = True
                    break
        item['has_tech_doc'] = hit

    return render(request, 'kho_san_pham/product_list.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': STATUS_CHOICES,
        'selected_type': product_type,
        'type_choices': PRODUCT_TYPE_CHOICES,
        'type_labels': PRODUCT_TYPE_LABELS,
        'has_filters': bool(search_query or status != 'all' or product_type),
        'expand_search_hits': bool(search_query),
    })


@module_perm_required(MODULE_KHO_SAN_PHAM, 'export')
def product_export(request):
    qs, *_ = _product_list_qs(request)
    return export_products_xlsx(qs)


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def product_import_template(request):
    return sample_template_xlsx()


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, post='create')
def product_import(request):
    if request.method != 'POST':
        return redirect('kho_san_pham:product_list')
    file_obj = request.FILES.get('excel_file')
    if not file_obj:
        messages.error(request, 'Chọn file Excel trước khi nhập.')
        return redirect('kho_san_pham:product_list')
    if not file_obj.name.lower().endswith(('.xlsx', '.xls')):
        messages.error(request, 'Chỉ chấp nhận file Excel (.xlsx hoặc .xls).')
        return redirect('kho_san_pham:product_list')
    try:
        result = import_products_from_excel(file_obj, user=request.user)
    except ProductImportError as exc:
        messages.error(request, str(exc))
        return redirect('kho_san_pham:product_list')

    if result['created'] or result['updated']:
        messages.success(
            request,
            f'Nhập xong: {result["created"]} mới, {result["updated"]} cập nhật.',
        )
    elif result['skipped'] and not result['errors']:
        messages.warning(request, 'Không có dòng hợp lệ nào được nhập.')
    if result['skipped'] and (result['created'] or result['updated'] or result['errors']):
        messages.info(request, f'Bỏ qua {result["skipped"]} dòng.')
    for err in result['errors']:
        messages.warning(request, err)
    if result['error_count'] > len(result['errors']):
        messages.warning(
            request,
            f'Còn {result["error_count"] - len(result["errors"])} lỗi khác (chỉ hiển thị 20 dòng đầu).',
        )
    return redirect('kho_san_pham:product_list')


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, post='update')
def product_import_accounting(request):
    """Nhập mã kế toán từ file HĐ / tem nhãn / Kiot (cột Mã sản phẩm)."""
    if request.method != 'POST':
        return redirect('kho_san_pham:product_list')
    file_obj = request.FILES.get('excel_file')
    if not file_obj:
        messages.error(request, 'Chọn file Excel trước khi nhập mã kế toán.')
        return redirect('kho_san_pham:product_list')
    if not file_obj.name.lower().endswith(('.xlsx', '.xls')):
        messages.error(request, 'Chỉ chấp nhận file Excel (.xlsx hoặc .xls).')
        return redirect('kho_san_pham:product_list')
    result = import_accounting_from_invoice_excel(file_obj)
    if result.updated:
        messages.success(
            request,
            f'Đã gán mã kế toán cho {result.updated} SKU '
            f'({result.styles_touched} Style).',
        )
    elif not result.errors and not result.unmatched_rows:
        messages.warning(request, 'Không có dòng nào để cập nhật.')
    if result.skipped and result.updated:
        messages.info(request, f'{result.skipped} SKU đã đúng mã — bỏ qua.')
    if result.unmatched_rows:
        messages.warning(
            request,
            f'{result.unmatched_rows} dòng trên file không khớp tên Kiot/HĐ.',
        )
    for err in result.errors[:15]:
        messages.warning(request, err)
    return redirect('kho_san_pham:product_list')


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, post='update')
def product_generate_barcodes(request):
    """Sinh mã vạch EAN-13 nội bộ cho toàn bộ (hoặc chỉ SP trống)."""
    from kho_san_pham.services.barcode import assign_barcodes_to_all_products

    if request.method != 'POST':
        return redirect('kho_san_pham:product_list')
    force = (request.POST.get('force') or '1').strip() != '0'
    result = assign_barcodes_to_all_products(force=force)
    if result.updated:
        messages.success(
            request,
            f'Đã gán {result.updated} mã vạch EAN-13'
            f'{" (tạo mới toàn bộ)" if force else " (chỉ SP trống)"}.',
        )
    else:
        messages.info(request, 'Không có sản phẩm nào cần gán mã vạch.')
    return redirect('kho_san_pham:product_list')


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def product_detail(request, pk: int):
    from kiotviet.formatters import format_description_html
    from hrm.module_permissions import (
        MODULE_SAN_XUAT,
        user_can_create_module,
        user_can_view_module,
    )
    from san_xuat.services.bom import get_working_bom
    from san_xuat.services.products import find_tech_doc_for_product, product_sx_code

    product = get_object_or_404(Product, pk=pk)
    tech_doc = find_tech_doc_for_product(product)
    working_bom = get_working_bom(tech_doc) if tech_doc else None
    sx_code = (tech_doc.product_code if tech_doc else product_sx_code(product)) or product.code

    return render(request, 'kho_san_pham/product_detail.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'product': product,
        'type_labels': PRODUCT_TYPE_LABELS,
        'description_html': format_description_html(product.description),
        'tech_doc': tech_doc,
        'working_bom': working_bom,
        'sx_code': sx_code,
        'can_view_sx': user_can_view_module(request.user, MODULE_SAN_XUAT),
        'can_create_sx': user_can_create_module(request.user, MODULE_SAN_XUAT),
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='create', post='create')
def product_create(request):
    initial = {'is_active': True}
    type_hint = (request.GET.get('type') or '').strip()
    if type_hint in PRODUCT_TYPE_LABELS:
        initial['product_type'] = type_hint
    else:
        initial['product_type'] = PRODUCT_TYPE_HANG_HOA
    form = ProductForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                product = form.save(commit=False)
                product.sync_source = SYNC_SOURCE_MANUAL
                product.created_by = request.user
                product.save()
                _apply_catalog_qty(product, form, user=request.user)
        except StockMovementError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Đã thêm sản phẩm {product.code}.')
            return redirect('kho_san_pham:product_detail', pk=product.pk)
    return render(request, 'kho_san_pham/product_form.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'form': form,
        'is_edit': False,
        'cancel_url': reverse('kho_san_pham:product_list'),
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def product_edit(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                product = form.save()
                _apply_catalog_qty(product, form, user=request.user)
        except StockMovementError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Đã cập nhật {product.code}.')
            return redirect('kho_san_pham:product_detail', pk=product.pk)
    return render(request, 'kho_san_pham/product_form.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'form': form,
        'is_edit': True,
        'product': product,
        'cancel_url': reverse('kho_san_pham:product_detail', args=[product.pk]),
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def product_deactivate(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.is_active = False
        product.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Đã ngừng dùng {product.code}.')
        return redirect('kho_san_pham:product_detail', pk=product.pk)
    return render(request, 'kho_san_pham/product_confirm_deactivate.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'product': product,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def product_reactivate(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.is_active = True
        product.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Đã dùng lại {product.code}.')
        return redirect('kho_san_pham:product_detail', pk=product.pk)
    return render(request, 'kho_san_pham/product_confirm_reactivate.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'product': product,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='delete', post='delete')
def product_delete(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if product.is_kv_synced:
        messages.error(request, 'Không xóa thành phẩm đồng bộ từ KiotViet — hãy ngừng dùng.')
        return redirect('kho_san_pham:product_detail', pk=product.pk)
    if request.method == 'POST':
        code = product.code
        product.delete()
        messages.success(request, f'Đã xóa {code}.')
        return redirect('kho_san_pham:product_list')
    return render(request, 'kho_san_pham/product_confirm_delete.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'product': product,
    })


@module_perm_required(MODULE_KHO_SAN_PHAM, 'create')
@require_POST
def product_sync_kv(request):
    result = sync_thanh_pham_from_kiotviet()
    if result.errors and not (result.created or result.updated):
        messages.error(request, f'Đồng bộ thất bại: {result.errors[0]}')
    else:
        msg = f'Đồng bộ thành phẩm từ KiotViet: {result.summary()}.'
        if result.errors:
            messages.warning(request, msg + f' ({len(result.errors)} lỗi)')
        else:
            messages.success(request, msg)
    return redirect('kho_san_pham:product_list')
