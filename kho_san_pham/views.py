from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
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
from kho_san_pham.sku_vocabulary import extract_sp_number
from kho_san_pham.services.barcode import allocate_barcode
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


# Lựa chọn trên thanh lọc — value = "sort:dir" để một select đủ cả chiều.
# SKU mặc định theo số SP (SP008484 trước SP008476), không theo tiền tố JP-SET-SC.
PRODUCT_LIST_ORDER_CHOICES = (
    ('code:desc', 'Số SP lớn → nhỏ'),
    ('code:asc', 'Số SP nhỏ → lớn'),
    ('qty_on_hand:desc', 'Tồn xưởng nhiều → ít'),
    ('qty_on_hand:asc', 'Tồn xưởng ít → nhiều'),
    ('name:asc', 'Tên A → Z'),
    ('base_price:desc', 'Giá cao → thấp'),
    ('base_price:asc', 'Giá thấp → cao'),
)


def _list_sort(request):
    """Đọc ``order=qty_on_hand:desc`` (ưu tiên) hoặc cặp ``sort`` + ``dir`` cũ."""
    order = (request.GET.get('order') or '').strip()
    if order and ':' in order:
        sort_key, _, sort_dir = order.partition(':')
        sort_key = sort_key.strip()
        sort_dir = sort_dir.strip().lower()
    else:
        sort_key = (request.GET.get('sort') or 'code').strip()
        sort_dir = (request.GET.get('dir') or '').strip().lower()
    if sort_key not in PRODUCT_LIST_SORT_FIELDS:
        sort_key = 'code'
    if sort_dir not in ('asc', 'desc'):
        # Tồn / giá / số SP: mặc định lớn → nhỏ; còn lại A → Z.
        sort_dir = 'desc' if sort_key in ('qty_on_hand', 'base_price', 'code') else 'asc'
    return sort_key, sort_dir


def _order_value(sort_key: str, sort_dir: str) -> str:
    return f'{sort_key}:{sort_dir}'


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
    if sort_key == 'code':
        from django.db.models import BigIntegerField
        from django.db.models.expressions import RawSQL

        qs = qs.annotate(
            _sp_num=RawSQL(
                "COALESCE((regexp_match(COALESCE(NULLIF(BTRIM(style_code), ''), code),"
                " 'SP([0-9]+)'))[1]::bigint, -1)",
                [],
                output_field=BigIntegerField(),
            )
        )
        sp_order = '-_sp_num' if sort_dir == 'desc' else '_sp_num'
        qs = qs.order_by(sp_order, 'style_code', 'code')
    else:
        order = PRODUCT_LIST_SORT_FIELDS[sort_key]
        if sort_dir == 'desc':
            order = f'-{order}'
        qs = qs.order_by(order, 'code')
    return qs, search_query, status, product_type, sort_key, sort_dir


def _group_sp_sort_key(group: dict) -> tuple:
    text = (group.get('style_code') or '').strip()
    if not text or text == '—':
        text = group.get('code') or ''
    return (extract_sp_number(text), text.upper())


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
    products = list(qs)
    groups = [format_style_group(g) for g in group_products_by_style(products)]
    # Sau khi gom, sắp lại theo số SP / tổng tồn / giá của nhóm — không theo SKU đầu tiên.
    reverse = sort_dir == 'desc'
    if sort_key == 'code':
        groups.sort(key=_group_sp_sort_key, reverse=reverse)
    elif sort_key == 'qty_on_hand':
        groups.sort(key=lambda g: g.get('qty_on_hand') or 0, reverse=reverse)
    elif sort_key == 'base_price':
        groups.sort(
            key=lambda g: g.get('min_price') if g.get('min_price') is not None else -1,
            reverse=reverse,
        )
    page_obj, query_string = paginate_queryset(request, groups, per_page=40)

    # Đánh dấu nhóm đã có hồ sơ thiết kế (theo mã SX / style)
    from django.db.models import Q
    from hrm.module_permissions import MODULE_SAN_XUAT, user_can_update_module
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

    selected_order = _order_value(sort_key, sort_dir)
    stock_sort_params = request.GET.copy()
    stock_sort_params.pop('page', None)
    stock_sort_params.pop('sort', None)
    stock_sort_params.pop('dir', None)
    if sort_key == 'qty_on_hand' and sort_dir == 'desc':
        stock_sort_params['order'] = 'qty_on_hand:asc'
    else:
        stock_sort_params['order'] = 'qty_on_hand:desc'
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
        'selected_order': selected_order,
        'order_choices': PRODUCT_LIST_ORDER_CHOICES,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'stock_sort_href': f'?{stock_sort_params.urlencode()}',
        'has_filters': bool(
            search_query or status != 'all' or product_type or selected_order != 'code:desc'
        ),
        'expand_search_hits': bool(search_query),
        'can_update_sx': user_can_update_module(request.user, MODULE_SAN_XUAT),
        'list_next': request.get_full_path(),
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
        user_can_update_module,
        user_can_view_module,
    )
    from san_xuat.services.bom import get_working_bom
    from san_xuat.services.products import find_tech_doc_for_product, product_sx_code

    from kho_san_pham.services.stock import product_stock_rows

    product = get_object_or_404(Product, pk=pk)
    tech_doc = find_tech_doc_for_product(product)
    working_bom = get_working_bom(tech_doc) if tech_doc else None
    sx_code = (tech_doc.product_code if tech_doc else product_sx_code(product)) or product.code

    return render(request, 'kho_san_pham/product_detail.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'product': product,
        'stock_rows': product_stock_rows(product),
        'type_labels': PRODUCT_TYPE_LABELS,
        'description_html': format_description_html(product.description),
        'tech_doc': tech_doc,
        'working_bom': working_bom,
        'sx_code': sx_code,
        'can_view_sx': user_can_view_module(request.user, MODULE_SAN_XUAT),
        'can_create_sx': user_can_create_module(request.user, MODULE_SAN_XUAT),
        'can_update_sx': user_can_update_module(request.user, MODULE_SAN_XUAT),
    })


def _redirect_after_product_sync(request, product):
    nxt = (request.POST.get('next') or '').strip()
    if nxt.startswith('/kho-san-pham/danh-muc'):
        return redirect(nxt)
    return redirect('kho_san_pham:product_detail', pk=product.pk)


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, post='update')
@require_POST
def product_sync_tech_doc(request, pk: int):
    from hrm.module_permissions import MODULE_SAN_XUAT, user_can_update_module
    from san_xuat.services.products import TechDocSyncError, sync_tech_doc_from_catalog

    product = get_object_or_404(Product, pk=pk)
    if not user_can_update_module(request.user, MODULE_SAN_XUAT):
        messages.error(request, 'Cần quyền cập nhật Sản xuất để đồng bộ hồ sơ thiết kế.')
        return _redirect_after_product_sync(request, product)
    try:
        result = sync_tech_doc_from_catalog(product=product, user=request.user)
    except TechDocSyncError as exc:
        messages.error(request, str(exc))
        return _redirect_after_product_sync(request, product)

    bits = result.changed or ['dữ liệu danh mục']
    msg = (
        f'Đã đồng bộ hồ sơ {result.doc.product_code}: '
        + ', '.join(bits)
        + '.'
    )
    extra = []
    if result.sku_created:
        extra.append(f'thêm {result.sku_created} SKU')
    if result.sku_updated:
        extra.append(f'cập nhật {result.sku_updated} SKU')
    if result.sku_linked:
        extra.append(f'gắn {result.sku_linked} SKU')
    if result.sku_retired:
        extra.append(f'ngừng {result.sku_retired} SKU cũ')
    if extra:
        msg += ' (' + '; '.join(extra) + ')'
    if result.warnings:
        messages.warning(request, msg + ' — ' + '; '.join(result.warnings[:3]))
    else:
        messages.success(request, msg)
    return _redirect_after_product_sync(request, product)


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


def _clone_form_initial(source: Product) -> dict:
    """Copy thuộc tính dùng chung; SKU / mã vạch / KV / tồn để trống — đổi màu/size rồi ghép mới."""
    return {
        'product_type': source.product_type,
        'catalog_type': source.catalog_type_id,
        'style_code': source.style_code,
        'color_code': source.color_code,
        'size_label': source.size_label,
        'accounting_code': source.accounting_code,
        'name': source.name,
        'full_name': source.full_name,
        'unit': source.unit,
        'category_name': source.category_name,
        'base_price': source.base_price,
        'description': source.description,
        'notes': source.notes,
        'is_active': True,
        'code': '',
        'bar_code': '',
        'kiotviet_code': '',
    }


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='create', post='create')
def product_duplicate(request, pk: int):
    source = get_object_or_404(Product, pk=pk)
    form = ProductForm(
        request.POST or None,
        request.FILES or None,
        initial=_clone_form_initial(source),
        clone_from=source,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                product = form.save(commit=False)
                product.sync_source = SYNC_SOURCE_MANUAL
                product.created_by = request.user
                product.gender = source.gender
                product.category_path = source.category_path
                product.allows_sale = source.allows_sale
                if not product.image and source.image:
                    product.image = source.image
                if not (product.image_url or '').strip():
                    product.image_url = source.image_url or ''
                if not (product.bar_code or '').strip():
                    product.bar_code = allocate_barcode()
                product.save()
                _apply_catalog_qty(product, form, user=request.user)
        except StockMovementError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Đã nhân bản {source.code} thành {product.code}.')
            return redirect('kho_san_pham:product_detail', pk=product.pk)
    return render(request, 'kho_san_pham/product_form.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'form': form,
        'is_edit': False,
        'is_duplicate': True,
        'source_product': source,
        'cancel_url': reverse('kho_san_pham:product_detail', args=[source.pk]),
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


def _product_delete_blockers(product: Product) -> list[str]:
    """Chỉ xóa SKU chưa có phát sinh kho; tồn rỗng không chặn."""
    checks = (
        ('Sổ kho', product.ledger_entries),
        ('Phiếu nhập', product.stock_receipt_lines),
    )
    blockers = [
        f'{label}: {manager.count()}'
        for label, manager in checks
        if manager.exists()
    ]
    nonzero_balances = product.stock_balances.exclude(qty_on_hand=0).count()
    if nonzero_balances:
        blockers.append(f'Tồn kho: {nonzero_balances}')
    return blockers


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='delete', post='delete')
def product_delete(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    blockers = _product_delete_blockers(product)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                product = get_object_or_404(
                    Product.objects.select_for_update(),
                    pk=pk,
                )
                blockers = _product_delete_blockers(product)
                if blockers:
                    messages.error(
                        request,
                        f'Không thể xóa {product.code} vì đã có dữ liệu phát sinh. '
                        'Hãy dùng “Ngừng dùng” để giữ lịch sử.',
                    )
                    return redirect('kho_san_pham:product_detail', pk=product.pk)
                code = product.code
                image = product.image
                product.stock_balances.filter(qty_on_hand=0).delete()
                product.delete()
                if image:
                    transaction.on_commit(lambda: image.delete(save=False))
        except ProtectedError:
            messages.error(
                request,
                f'Không thể xóa {product.code} vì đang được dữ liệu khác sử dụng.',
            )
            return redirect('kho_san_pham:product_detail', pk=pk)
        messages.success(request, f'Đã xóa {code}.')
        return redirect('kho_san_pham:product_list')
    return render(request, 'kho_san_pham/product_confirm_delete.html', {
        **nav_context('products', user=request.user),
        **perm_context(request.user, 'products'),
        'product': product,
        'delete_blockers': blockers,
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
