from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.forms import MaterialForm
from kho_npl.models import Material, MaterialCategory
from kho_npl.services.stock import material_stock_rows, material_total_qty
from kho_npl.view_utils import nav_context, perm_context


@module_perm_required(MODULE_KHO_NPL, 'view')
def material_list(request):
    search_query = get_search_query(request)
    category_id = request.GET.get('category', '').strip()
    show_inactive = request.GET.get('inactive') == '1'
    qs = Material.objects.select_related('category', 'unit', 'supplier')
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if category_id.isdigit():
        qs = qs.filter(category_id=int(category_id))
    if search_query:
        qs = qs.filter(
            Q(code__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(color__icontains=search_query)
            | Q(specification__icontains=search_query)
        )
    rows = material_stock_rows(qs)
    page_obj, query_string = paginate_queryset(request, rows, per_page=25)
    categories = MaterialCategory.objects.filter(is_active=True)
    return render(request, 'kho_npl/material_list.html', {
        **nav_context('materials'),
        **perm_context(request.user),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'categories': categories,
        'selected_category': category_id,
        'show_inactive': show_inactive,
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
        **nav_context('materials'),
        **perm_context(request.user),
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
        **nav_context('materials'),
        **perm_context(request.user),
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
        **nav_context('materials'),
        **perm_context(request.user),
        'form': form,
        'is_edit': True,
        'material': material,
        'cancel_url': reverse('kho_npl:material_detail', args=[material.pk]),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='delete', post='delete')
def material_deactivate(request, pk):
    material = get_object_or_404(Material, pk=pk)
    if request.method == 'POST':
        material.is_active = False
        material.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Đã ngừng sử dụng {material.code}.')
        return redirect('kho_npl:material_list')
    return render(request, 'kho_npl/material_confirm_deactivate.html', {
        **nav_context('materials'),
        **perm_context(request.user),
        'material': material,
    })
