import pandas as pd
from decimal import Decimal

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from kho_npl.material_search import apply_material_search
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import (
    STOCK_STATUS_LABELS,
    STOCK_STATUS_LOW,
    STOCK_STATUS_OK,
    STOCK_STATUS_OUT,
)
from kho_npl.forms import MaterialForm
from kho_npl.material_list_columns import (
    MATERIAL_LIST_COLUMNS,
    MATERIAL_LIST_SORT_FIELDS,
    MATERIAL_LIST_TOTAL_COL_WEIGHT,
)
from kho_npl.models import Material, MaterialCategory, StockBalance, WarehouseLocation
from kho_npl.services.adjustments import balance_qty
from kho_npl.catalog_labels import color_label, spec_label, unit_label
from kho_npl.templatetags.npl_extras import format_npl_qty
from kho_npl.services.excel_export import dataframe_to_xlsx_response
from kho_npl.services.material_import_export import (
    MaterialImportError,
    export_materials_xlsx,
    import_materials_from_excel,
    sample_template_xlsx,
)
from kho_npl.services.scrap_warehouse import filter_storage_location_ids, source_locations_qs
from kho_npl.services.stock import material_stock_rows
from kho_npl.stock_list_columns import (
    STOCK_LIST_COLUMNS,
    STOCK_LIST_SORT_FIELDS,
    STOCK_LIST_TOTAL_COL_WEIGHT,
)
from kho_npl.category_tree import (
    active_category_roots,
    category_filter_q,
    parse_category_cascade_filter,
    resolve_category_filter_q,
)
from kho_npl.filter_utils import parse_int_ids
from kho_npl.doc_prefill import stock_doc_action_urls, stock_doc_prefill_location
from kho_npl.view_utils import nav_context, perm_context


def _material_search_label(material: Material) -> str:
    return f'{material.code} — {material.name} ({material.unit.name})'


def _material_stock_label(material: Material, qty: Decimal) -> str:
    unit = unit_label(material.unit)
    qty_text = format_npl_qty(qty)
    if unit:
        return f'{material.name} — {qty_text} {unit}'
    return f'{material.name} — {qty_text}'


def _material_qty_label(material: Material, qty: Decimal) -> str:
    unit = unit_label(material.unit)
    qty_text = format_npl_qty(qty)
    if unit:
        return f'{qty_text} {unit}'
    return qty_text


def _parse_positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_search(request):
    q = (request.GET.get('q') or '').strip()
    location_id = _parse_positive_int(request.GET.get('location_id'))
    in_stock_only = (request.GET.get('in_stock_only') or '').strip().lower() in ('1', 'true', 'yes')
    if location_id and in_stock_only:
        qs = (
            Material.objects.filter(
                is_active=True,
                balances__location_id=location_id,
                balances__quantity__gt=0,
            )
            .select_related('unit', 'color', 'specification')
            .distinct()
        )
        if q:
            qs = apply_material_search(qs, q)
        browse_limit = 1000 if not q else 50
        materials = list(qs.order_by('name', 'code')[:browse_limit])
        balance_map = {
            balance.material_id: balance.quantity
            for balance in StockBalance.objects.filter(
                location_id=location_id,
                material_id__in=[material.pk for material in materials],
            )
        }
    else:
        qs = Material.objects.filter(is_active=True).select_related('unit', 'color', 'specification')
        if q:
            qs = apply_material_search(qs, q)
        if location_id and not q:
            browse_limit = 1000
        elif q:
            browse_limit = 50
        else:
            browse_limit = 40
        materials = list(qs.order_by('name', 'code')[:browse_limit])
        balance_map = {}
        if location_id and materials:
            material_ids = [m.pk for m in materials]
            for balance in StockBalance.objects.filter(
                location_id=location_id,
                material_id__in=material_ids,
            ):
                balance_map[balance.material_id] = balance.quantity
    rows = []
    for material in materials:
        if location_id is not None:
            qty = balance_map.get(material.pk, Decimal('0'))
            if in_stock_only and qty <= 0:
                continue
            text = _material_stock_label(material, qty)
        else:
            text = _material_search_label(material)
        rows.append({
            'id': material.pk,
            'text': text,
            'code': material.code,
            'name': material.name,
            'unit': unit_label(material.unit),
            'unit_name': material.unit.name,
            'specification': spec_label(material.specification) if material.specification_id else '',
            'specification_name': material.specification.name if material.specification_id else '',
            'color': color_label(material.color) if material.color_id else '',
            'qty': float(balance_map.get(material.pk, Decimal('0'))) if location_id is not None else None,
            'qty_label': (
                _material_qty_label(material, balance_map.get(material.pk, Decimal('0')))
                if location_id is not None
                else ''
            ),
        })
    return JsonResponse({'results': rows})


@module_perm_required(MODULE_KHO_NPL, 'view')
def balance_lookup(request):
    material_id = _parse_positive_int(request.GET.get('material_id'))
    location_id = _parse_positive_int(request.GET.get('location_id'))
    if not material_id or not location_id:
        return JsonResponse({'error': 'Thiếu material_id hoặc location_id.'}, status=400)
    try:
        material = Material.objects.select_related('unit').get(pk=material_id, is_active=True)
        location = WarehouseLocation.objects.get(pk=location_id, is_active=True)
    except (Material.DoesNotExist, WarehouseLocation.DoesNotExist):
        return JsonResponse({'error': 'NPL hoặc vị trí không hợp lệ.'}, status=404)
    qty = balance_qty(material, location)
    return JsonResponse({
        'qty': format_npl_qty(qty),
        'qty_decimal': str(qty),
        'unit': unit_label(material.unit),
        'unit_name': material.unit.name,
        'qty_label': _material_qty_label(material, qty),
        'text': _material_stock_label(material, qty),
        'name': material.name,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def batch_lookup(request):
    """Danh sách lô còn tồn của 1 NPL — cho dropdown phiếu xuất/hủy/điều chỉnh/kiểm kê."""
    material_id = _parse_positive_int(request.GET.get('material_id'))
    if not material_id:
        return JsonResponse({'error': 'Thiếu material_id.'}, status=400)
    try:
        material = Material.objects.get(pk=material_id, is_active=True)
    except Material.DoesNotExist:
        return JsonResponse({'error': 'NPL không hợp lệ.'}, status=404)
    from kho_npl.services.batches import batch_stock_options
    return JsonResponse({'results': batch_stock_options(material)})


def _material_catalog_qs(request):
    search_query = get_search_query(request)
    category_parent_id, category_ids = parse_category_cascade_filter(request)
    show_inactive = request.GET.get('inactive') == '1'
    qs = Material.objects.select_related('category', 'unit', 'supplier', 'color', 'specification')
    if not show_inactive:
        qs = qs.filter(is_active=True)
    category_q = resolve_category_filter_q(category_parent_id, category_ids)
    if category_q:
        qs = qs.filter(category_q)
    if search_query:
        qs = apply_material_search(qs, search_query)
    return qs, search_query, category_ids, category_parent_id, show_inactive


MATERIAL_LIST_STATUS_CHOICES = (
    ('all', 'Tất cả'),
    ('active', 'Đang dùng'),
    ('inactive', 'Ngừng dùng'),
)


def _material_list_status(request) -> str:
    status = (request.GET.get('status') or 'all').strip().lower()
    if status not in {key for key, _ in MATERIAL_LIST_STATUS_CHOICES}:
        return 'all'
    return status


def _material_list_sort(request):
    sort_key = (request.GET.get('sort') or 'code').strip()
    sort_dir = (request.GET.get('dir') or 'asc').strip().lower()
    if sort_key not in MATERIAL_LIST_SORT_FIELDS:
        sort_key = 'code'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'
    orm_field = MATERIAL_LIST_SORT_FIELDS[sort_key]
    order = orm_field if sort_dir == 'asc' else f'-{orm_field}'
    return sort_key, sort_dir, order


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_list(request):
    search_query = get_search_query(request)
    category_ids = parse_int_ids(request, 'category')
    status = _material_list_status(request)
    qs = Material.objects.select_related('category', 'unit', 'supplier', 'color', 'specification')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    if category_ids:
        qs = qs.filter(category_filter_q(category_ids))
    if search_query:
        qs = apply_material_search(qs, search_query)
    sort_key, sort_dir, order_by = _material_list_sort(request)
    page_obj, query_string = paginate_queryset(request, qs.order_by(order_by, 'code'), per_page=25)
    category_roots = active_category_roots()
    return render(request, 'kho_npl/material_list.html', {
        **nav_context('materials', user=request.user),
        **perm_context(request.user, 'materials'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'category_roots': category_roots,
        'selected_categories': category_ids,
        'selected_status': status,
        'status_choices': MATERIAL_LIST_STATUS_CHOICES,
        'list_columns': MATERIAL_LIST_COLUMNS,
        'total_col_weight': MATERIAL_LIST_TOTAL_COL_WEIGHT,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'has_filters': bool(search_query or category_ids or status != 'all'),
    })


MATERIAL_STOCK_STATUS_CHOICES = (
    ('', 'Tất cả'),
    (STOCK_STATUS_OK, 'Đủ hàng'),
    (STOCK_STATUS_LOW, 'Sắp thiếu'),
    (STOCK_STATUS_OUT, 'Hết hàng'),
)


def _stock_list_sort(request):
    sort_key = (request.GET.get('sort') or 'code').strip()
    sort_dir = (request.GET.get('dir') or 'asc').strip().lower()
    if sort_key not in STOCK_LIST_SORT_FIELDS:
        sort_key = 'code'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'
    return sort_key, sort_dir


def _stock_filtered_rows(request):
    qs, search_query, category_ids, category_parent_id, show_inactive = _material_catalog_qs(request)
    location_ids = filter_storage_location_ids(parse_int_ids(request, 'location'))
    status = (request.GET.get('status') or '').strip().lower()
    if status not in (STOCK_STATUS_OK, STOCK_STATUS_LOW, STOCK_STATUS_OUT):
        status = ''
    if location_ids:
        qs = qs.filter(balances__location_id__in=location_ids).distinct()

    rows = material_stock_rows(qs, location_ids=location_ids or None)
    if status:
        rows = [r for r in rows if r['status'] == status]

    sort_key, sort_dir = _stock_list_sort(request)
    rows.sort(key=STOCK_LIST_SORT_FIELDS[sort_key], reverse=(sort_dir == 'desc'))
    return rows, search_query, category_ids, category_parent_id, location_ids, status, show_inactive, sort_key, sort_dir


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_stock_list(request):
    rows, search_query, category_ids, category_parent_id, location_ids, status, show_inactive, sort_key, sort_dir = (
        _stock_filtered_rows(request)
    )
    page_obj, query_string = paginate_queryset(request, rows, per_page=25)
    return render(request, 'kho_npl/material_stock.html', {
        **nav_context('material_stock', user=request.user),
        **perm_context(request.user, 'material_stock'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'category_roots': active_category_roots(),
        'locations': source_locations_qs(),
        'selected_categories': category_ids,
        'selected_locations': location_ids,
        'selected_status': status,
        'status_choices': MATERIAL_STOCK_STATUS_CHOICES,
        'show_inactive': show_inactive,
        'list_columns': STOCK_LIST_COLUMNS,
        'total_col_weight': STOCK_LIST_TOTAL_COL_WEIGHT,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'has_filters': bool(search_query or category_ids or location_ids or status),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_stock_detail(request, pk):
    material = get_object_or_404(
        Material.objects.select_related(
            'category', 'unit', 'color', 'specification',
        ),
        pk=pk,
    )
    location_ids = filter_storage_location_ids(parse_int_ids(request, 'location'))
    rows = material_stock_rows(
        Material.objects.filter(pk=pk),
        location_ids=location_ids or None,
    )
    row = rows[0]
    from kho_npl.services.batches import batches_with_stock, material_batch_totals
    batches = list(batches_with_stock(material))
    _bq, stock_value, avg_unit_price = material_batch_totals(material)
    back_query = request.GET.urlencode()
    stock_card_params = [f'material={pk}']
    for loc_id in location_ids:
        stock_card_params.append(f'location={loc_id}')
    stock_card_url = reverse('kho_npl:stock_cards') + '?' + '&'.join(stock_card_params)
    prefill_location_id = stock_doc_prefill_location(request, row)
    issue_create_url, transfer_create_url = stock_doc_action_urls(pk, prefill_location_id)
    issue_perms = perm_context(request.user, 'issues')
    transfer_perms = perm_context(request.user, 'transfers')
    return render(request, 'kho_npl/material_stock_detail.html', {
        **nav_context('material_stock', user=request.user),
        **perm_context(request.user, 'material_stock'),
        'material': material,
        'row': row,
        'batches': batches,
        'avg_unit_price': avg_unit_price,
        'stock_value': stock_value,
        'back_query': back_query,
        'stock_card_url': stock_card_url,
        'selected_locations': location_ids,
        'issue_create_url': issue_create_url,
        'transfer_create_url': transfer_create_url,
        'can_create_issue': issue_perms.get('can_create'),
        'can_create_transfer': transfer_perms.get('can_create'),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def material_stock_export(request):
    rows, _, _, _, _, _, _, _ = _stock_filtered_rows(request)
    data = []
    for row in rows:
        mat = row['material']
        data.append({
            'Mã NPL': mat.code,
            'Tên NPL': mat.name,
            'Nhóm': mat.category.name if mat.category_id else '',
            'Màu': mat.color.name if mat.color_id else '',
            'Quy cách': spec_label(mat.specification) if mat.specification_id else '',
            'ĐVT': mat.unit.name,
            'Tồn hiện tại': float(row['total_qty']),
            'Đơn giá BQ': float(row.get('avg_unit_price') or 0),
            'Giá trị tồn': float(row.get('stock_value') or 0),
            'Tối thiểu': float(mat.min_stock),
            'Vị trí chính': row['primary_location'],
            'Trạng thái': STOCK_STATUS_LABELS[row['status']],
        })
    df = pd.DataFrame(data)
    return dataframe_to_xlsx_response(df, 'Ton_kho_npl', 'Ton_kho')


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_detail(request, pk):
    material = get_object_or_404(
        Material.objects.select_related('category', 'unit', 'supplier', 'color', 'specification'),
        pk=pk,
    )
    return render(request, 'kho_npl/material_detail.html', {
        **nav_context('materials', user=request.user),
        **perm_context(request.user, 'materials'),
        'material': material,
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def material_create(request):
    form = MaterialForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        material = form.save()
        messages.success(request, f'Đã thêm nguyên phụ liệu {material.code}.')
        return redirect('kho_npl:material_detail', pk=material.pk)
    return render(request, 'kho_npl/material_form.html', {
        **nav_context('materials', user=request.user),
        **perm_context(request.user, 'materials'),
        'form': form,
        'is_edit': False,
        'cancel_url': reverse('kho_npl:material_list'),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def material_edit(request, pk):
    material = get_object_or_404(Material, pk=pk)
    form = MaterialForm(request.POST or None, request.FILES or None, instance=material)
    if request.method == 'POST' and form.is_valid():
        material = form.save()
        messages.success(request, f'Đã cập nhật {material.code}.')
        return redirect('kho_npl:material_detail', pk=material.pk)
    return render(request, 'kho_npl/material_form.html', {
        **nav_context('materials', user=request.user),
        **perm_context(request.user, 'materials'),
        'form': form,
        'is_edit': True,
        'material': material,
        'cancel_url': reverse('kho_npl:material_detail', args=[material.pk]),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def material_export(request):
    qs, _, _, _, _ = _material_catalog_qs(request)
    return export_materials_xlsx(qs)


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_import_template(request):
    return sample_template_xlsx()


@module_perm_required_methods(MODULE_KHO_NPL, post='create')
def material_import(request):
    if request.method != 'POST':
        return redirect('kho_npl:material_list')
    file_obj = request.FILES.get('excel_file')
    if not file_obj:
        messages.error(request, 'Chọn file Excel trước khi nhập.')
        return redirect('kho_npl:material_list')
    if not file_obj.name.lower().endswith(('.xlsx', '.xls')):
        messages.error(request, 'Chỉ chấp nhận file Excel (.xlsx hoặc .xls).')
        return redirect('kho_npl:material_list')
    try:
        result = import_materials_from_excel(file_obj)
    except MaterialImportError as exc:
        messages.error(request, str(exc))
        return redirect('kho_npl:material_list')

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
    return redirect('kho_npl:material_list')


@module_perm_required_methods(MODULE_KHO_NPL, get='delete', post='delete')
def material_deactivate(request, pk):
    material = get_object_or_404(Material, pk=pk)
    if request.method == 'POST':
        material.is_active = False
        material.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Đã ngừng sử dụng {material.code}.')
        return redirect('kho_npl:material_list')
    return render(request, 'kho_npl/material_confirm_deactivate.html', {
        **nav_context('materials', user=request.user),
        **perm_context(request.user, 'materials'),
        'material': material,
    })
