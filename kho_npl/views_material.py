from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import STOCK_STATUS_LOW, STOCK_STATUS_OK, STOCK_STATUS_OUT
from kho_npl.forms import MaterialForm
from kho_npl.material_list_columns import MATERIAL_LIST_COLUMNS
from kho_npl.models import Material, MaterialCategory, WarehouseLocation
from kho_npl.services.material_import_export import (
    MaterialImportError,
    export_materials_xlsx,
    import_materials_from_excel,
    sample_template_xlsx,
)
from kho_npl.services.stock import material_stock_rows, material_total_qty
from kho_npl.filter_utils import append_filter_params, parse_int_ids
from kho_npl.view_utils import nav_context, perm_context


def _material_search_label(material: Material) -> str:
    return f'{material.code} — {material.name} ({material.unit.code})'


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_search(request):
    q = (request.GET.get('q') or '').strip()
    qs = Material.objects.filter(is_active=True).select_related('unit')
    if q:
        qs = qs.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(color__icontains=q)
            | Q(specification__icontains=q),
        )
    rows = [
        {
            'id': m.pk,
            'text': _material_search_label(m),
            'code': m.code,
            'name': m.name,
            'unit': m.unit.code,
        }
        for m in qs.order_by('code')[:40]
    ]
    return JsonResponse({'results': rows})


def _material_catalog_qs(request):
    search_query = get_search_query(request)
    category_ids = parse_int_ids(request, 'category')
    show_inactive = request.GET.get('inactive') == '1'
    qs = Material.objects.select_related('category', 'unit', 'supplier')
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if category_ids:
        qs = qs.filter(category_id__in=category_ids)
    if search_query:
        qs = qs.filter(
            Q(code__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(color__icontains=search_query)
            | Q(specification__icontains=search_query)
        )
    return qs, search_query, category_ids, show_inactive


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_list(request):
    qs, search_query, category_ids, show_inactive = _material_catalog_qs(request)
    page_obj, query_string = paginate_queryset(request, qs.order_by('code'), per_page=25)
    categories = MaterialCategory.objects.filter(is_active=True)
    return render(request, 'kho_npl/material_list.html', {
        **nav_context('materials', user=request.user),
        **perm_context(request.user, 'materials'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'categories': categories,
        'selected_categories': category_ids,
        'show_inactive': show_inactive,
        'list_columns': MATERIAL_LIST_COLUMNS,
        'row_count': page_obj.paginator.count,
        'has_filters': bool(search_query or category_ids or show_inactive),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_stock_list(request):
    qs, search_query, category_ids, show_inactive = _material_catalog_qs(request)
    location_ids = parse_int_ids(request, 'location')
    status = (request.GET.get('status') or '').strip().lower()
    if status not in (STOCK_STATUS_OK, STOCK_STATUS_LOW, STOCK_STATUS_OUT):
        status = ''
    if location_ids:
        qs = qs.filter(balances__location_id__in=location_ids).distinct()

    rows = material_stock_rows(qs, location_ids=location_ids or None)
    if status:
        rows = [r for r in rows if r['status'] == status]

    page_obj, query_string = paginate_queryset(request, rows, per_page=30)
    return render(request, 'kho_npl/material_stock.html', {
        **nav_context('material_stock', user=request.user),
        **perm_context(request.user, 'material_stock'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'categories': MaterialCategory.objects.filter(is_active=True),
        'locations': WarehouseLocation.objects.filter(is_active=True),
        'selected_categories': category_ids,
        'selected_locations': location_ids,
        'selected_status': status,
        'show_inactive': show_inactive,
        'total_rows': len(rows),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_detail(request, pk):
    material = get_object_or_404(
        Material.objects.select_related('category', 'unit', 'supplier'),
        pk=pk,
    )
    balances = material.balances.select_related('location').order_by('-quantity')
    total_qty = material_total_qty(material)
    return render(request, 'kho_npl/material_detail.html', {
        **nav_context('materials', user=request.user),
        **perm_context(request.user, 'materials'),
        'material': material,
        'balances': balances,
        'total_qty': total_qty,
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
    qs, _, _, _ = _material_catalog_qs(request)
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
        messages.error(request, 'Chọn file Excel để import.')
        return redirect('kho_npl:material_list')
    try:
        result = import_materials_from_excel(file_obj)
    except MaterialImportError as exc:
        messages.error(request, str(exc))
        return redirect('kho_npl:material_list')

    msg = f'Import xong: thêm {result["created"]}, cập nhật {result["updated"]}, bỏ qua {result["skipped"]}.'
    if result['errors']:
        msg += f' Có {result["error_count"]} lỗi (hiển thị tối đa 20 dòng đầu).'
        for err in result['errors']:
            messages.warning(request, err)
    messages.success(request, msg)
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
