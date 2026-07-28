"""Views thiết lập cấu trúc mã Style / loại / map KV."""

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_SAN_PHAM
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_san_pham.catalog_forms import (
    ProductStyleCreateForm,
    ProductStyleEditForm,
    ProductTypeForm,
    ProductTypeKvMapForm,
)
from kho_san_pham.catalog_models import ProductStyle, ProductType, ProductTypeKvMap
from kho_san_pham.view_utils import nav_context, perm_context


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def code_settings_hub(request):
    type_count = ProductType.objects.filter(is_active=True).count()
    style_count = ProductStyle.objects.filter(is_active=True).count()
    map_count = ProductTypeKvMap.objects.filter(is_active=True).count()
    return render(request, 'kho_san_pham/code_settings_hub.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'type_count': type_count,
        'style_count': style_count,
        'map_count': map_count,
    })


# —— Loại sản phẩm ——

@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def type_list(request):
    search_query = get_search_query(request)
    show_inactive = request.GET.get('inactive') == '1'
    qs = ProductType.objects.all()
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if search_query:
        qs = qs.filter(Q(code__icontains=search_query) | Q(name__icontains=search_query))
    qs = qs.annotate(
        style_count=Count('styles', distinct=True),
        product_count=Count('products', distinct=True),
    ).order_by('sort_order', 'code')
    page_obj, query_string = paginate_queryset(request, qs, per_page=40)
    return render(request, 'kho_san_pham/type_list.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'show_inactive': show_inactive,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='create', post='create')
def type_create(request):
    form = ProductTypeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Đã thêm loại {obj.code}.')
        return redirect('kho_san_pham:type_list')
    return render(request, 'kho_san_pham/type_form.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'form': form,
        'is_edit': False,
        'cancel_url': reverse('kho_san_pham:type_list'),
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def type_edit(request, pk):
    obj = get_object_or_404(ProductType, pk=pk)
    form = ProductTypeForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Đã cập nhật loại {obj.code}.')
        return redirect('kho_san_pham:type_list')
    return render(request, 'kho_san_pham/type_form.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'form': form,
        'is_edit': True,
        'cancel_url': reverse('kho_san_pham:type_list'),
    })


# —— Style ——

@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def style_list(request):
    search_query = get_search_query(request)
    show_inactive = request.GET.get('inactive') == '1'
    type_filter = (request.GET.get('type') or '').strip().upper()
    qs = ProductStyle.objects.select_related('product_type')
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if type_filter:
        qs = qs.filter(product_type__code__iexact=type_filter)
    if search_query:
        qs = qs.filter(
            Q(code__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(root_kiotviet_code__icontains=search_query)
        )
    qs = qs.order_by('code')
    page_obj, query_string = paginate_queryset(request, qs, per_page=40)
    types = ProductType.objects.filter(is_active=True).order_by('sort_order', 'code')
    return render(request, 'kho_san_pham/style_list.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'show_inactive': show_inactive,
        'types': types,
        'selected_type': type_filter,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='create', post='create')
def style_create(request):
    form = ProductStyleCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            style = form.save(user=request.user)
        except Exception as exc:  # noqa: BLE001 — ValidationError from form.save
            form.add_error(None, str(exc))
        else:
            messages.success(request, f'Đã tạo Style {style.code}.')
            return redirect('kho_san_pham:style_list')
    return render(request, 'kho_san_pham/style_form.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'form': form,
        'is_edit': False,
        'cancel_url': reverse('kho_san_pham:style_list'),
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def style_edit(request, pk):
    obj = get_object_or_404(ProductStyle, pk=pk)
    form = ProductStyleEditForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Đã cập nhật Style {obj.code}.')
        return redirect('kho_san_pham:style_list')
    return render(request, 'kho_san_pham/style_form.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'form': form,
        'is_edit': True,
        'style': obj,
        'cancel_url': reverse('kho_san_pham:style_list'),
    })


# —— Map KV ——

@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def kv_map_list(request):
    search_query = get_search_query(request)
    show_inactive = request.GET.get('inactive') == '1'
    qs = ProductTypeKvMap.objects.select_related('product_type')
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if search_query:
        qs = qs.filter(
            Q(match_value__icontains=search_query)
            | Q(product_type__code__icontains=search_query)
            | Q(notes__icontains=search_query)
        )
    qs = qs.order_by('priority', 'match_value')
    page_obj, query_string = paginate_queryset(request, qs, per_page=40)
    return render(request, 'kho_san_pham/kv_map_list.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'show_inactive': show_inactive,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='create', post='create')
def kv_map_create(request):
    form = ProductTypeKvMapForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Đã thêm map «{obj.match_value}» → {obj.product_type.code}.')
        return redirect('kho_san_pham:kv_map_list')
    return render(request, 'kho_san_pham/kv_map_form.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'form': form,
        'is_edit': False,
        'cancel_url': reverse('kho_san_pham:kv_map_list'),
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def kv_map_edit(request, pk):
    obj = get_object_or_404(ProductTypeKvMap, pk=pk)
    form = ProductTypeKvMapForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Đã cập nhật map.')
        return redirect('kho_san_pham:kv_map_list')
    return render(request, 'kho_san_pham/kv_map_form.html', {
        **nav_context('code_settings', user=request.user),
        **perm_context(request.user, 'code_settings'),
        'form': form,
        'is_edit': True,
        'cancel_url': reverse('kho_san_pham:kv_map_list'),
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='delete', post='delete')
@require_POST
def kv_map_delete(request, pk):
    obj = get_object_or_404(ProductTypeKvMap, pk=pk)
    label = obj.match_value
    obj.delete()
    messages.success(request, f'Đã xóa map «{label}».')
    return redirect('kho_san_pham:kv_map_list')


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
@require_POST
def assign_codes_from_maps(request):
    """Gán loại + sinh Style/SKU cho SP sync KV còn mã tạm (code = kiotviet_code)."""
    from kho_san_pham.services.sync_from_kiotviet import apply_style_sku_for_existing_products

    result = apply_style_sku_for_existing_products()
    messages.success(
        request,
        f'Gán mã: cập nhật {result.updated} · bỏ qua {result.skipped}'
        + (f' · lỗi {len(result.errors)}' if result.errors else ''),
    )
    return redirect('kho_san_pham:code_settings_hub')
