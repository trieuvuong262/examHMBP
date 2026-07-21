from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from assessment.decorators import module_perm_required
from hrm.module_permissions import (
    MODULE_SAN_XUAT,
    user_can_create_module,
    user_can_export_module,
    user_can_print_module,
    user_can_update_module,
)
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from san_xuat.forms import (
    BomLineFormSet,
    BomVersionMetaForm,
    ProcessStepFormSet,
    ProductTechDocCreateForm,
)
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.bom import (
    BomError,
    activate_bom,
    create_tech_doc,
    get_working_bom,
)
from san_xuat.services.costing import compute_costing, save_costing_snapshot
from san_xuat.services.products import search_kv_products


def _perm_ctx(request):
    return {
        'can_create': user_can_create_module(request.user, MODULE_SAN_XUAT),
        'can_update': user_can_update_module(request.user, MODULE_SAN_XUAT),
        'can_print': user_can_print_module(request.user, MODULE_SAN_XUAT),
        'can_export': user_can_export_module(request.user, MODULE_SAN_XUAT),
    }


@module_perm_required(MODULE_SAN_XUAT, 'view')
def hub(request):
    return redirect('san_xuat:overview')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def doc_list(request):
    from san_xuat.list_filters import (
        SX_FILTER_TECH_DOC,
        apply_sx_list_filters,
        parse_sx_list_filters,
        sx_filter_context,
    )
    from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context

    search_query = get_search_query(request)
    filters = parse_sx_list_filters(request)
    qs = ProductTechDoc.objects.all()
    qs = apply_sx_list_filters(qs, filters, SX_FILTER_TECH_DOC)
    qs = apply_term_search(
        qs,
        search_query,
        'product_code__icontains',
        'product_name__icontains',
        'notes__icontains',
    )
    qs = apply_sx_list_sort(qs, request, 'doc_list')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/doc_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'total_count': ProductTechDoc.objects.count(),
        **sx_filter_context(filters),
        **sx_list_grid_context(request, 'doc_list'),
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def bom_list(request):
    """Danh sách phiên bản BOM / định mức — khác danh sách hồ sơ SX."""
    from django.db.models import Count

    from san_xuat.list_filters import (
        SX_FILTER_BOM,
        apply_sx_list_filters,
        parse_sx_list_filters,
        sx_filter_context,
    )

    from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context

    filters = parse_sx_list_filters(request)
    status = (request.GET.get('status') or '').strip().lower()
    qs = (
        BomVersion.objects.select_related('tech_doc')
        .annotate(
            line_count=Count('lines', distinct=True),
            step_count=Count('process_steps', distinct=True),
        )
    )
    if status in {
        BomVersion.STATUS_DRAFT,
        BomVersion.STATUS_ACTIVE,
        BomVersion.STATUS_ARCHIVED,
    }:
        qs = qs.filter(status=status)
    qs = apply_sx_list_filters(qs, filters, SX_FILTER_BOM)
    qs = apply_sx_list_sort(qs, request, 'bom_list')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/bom_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'filter_status': status,
        'status_choices': BomVersion.STATUS_CHOICES,
        'list_filter_status_options': [('', 'Tất cả'), *BomVersion.STATUS_CHOICES],
        'list_filter_status_value': status,
        'total_count': BomVersion.objects.count(),
        **sx_filter_context(filters),
        **sx_list_grid_context(request, 'bom_list'),
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def doc_create(request):
    if request.method == 'POST':
        form = ProductTechDocCreateForm(request.POST)
        if form.is_valid():
            try:
                doc = create_tech_doc(
                    product_code=form.cleaned_data['product_code'],
                    notes=form.cleaned_data.get('notes') or '',
                    user=request.user,
                )
            except BomError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo hồ sơ SX {doc.product_code}.')
                return redirect('san_xuat:doc_detail', pk=doc.pk)
    else:
        initial = {}
        code = (request.GET.get('code') or '').strip()
        if code:
            initial['product_code'] = code
        form = ProductTechDocCreateForm(initial=initial)
    return render(request, 'san_xuat/doc_create.html', {
        'form': form,
        **_perm_ctx(request),
    })


def _get_bom_for_doc(doc: ProductTechDoc, bom_id: str | None) -> BomVersion | None:
    if bom_id:
        try:
            return doc.bom_versions.prefetch_related('lines__material', 'process_steps').get(pk=int(bom_id))
        except (ValueError, BomVersion.DoesNotExist):
            return None
    return get_working_bom(doc)


@module_perm_required(MODULE_SAN_XUAT, 'view')
def doc_detail(request, pk):
    doc = get_object_or_404(ProductTechDoc, pk=pk)
    tab = (request.GET.get('tab') or 'bom').strip().lower()
    if tab not in ('bom', 'process', 'costing'):
        tab = 'bom'

    bom = _get_bom_for_doc(doc, request.GET.get('bom'))
    versions = list(doc.bom_versions.order_by('-created_at'))
    costing = compute_costing(bom) if bom else None
    snapshots = list(bom.costing_snapshots.all()[:10]) if bom else []

    line_formset = None
    step_formset = None
    meta_form = None
    can_update = user_can_update_module(request.user, MODULE_SAN_XUAT)

    if bom and can_update and request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save_bom' and tab == 'bom':
            meta_form = BomVersionMetaForm(request.POST, instance=bom)
            line_formset = BomLineFormSet(request.POST, instance=bom, prefix='lines')
            if meta_form.is_valid() and line_formset.is_valid():
                meta_form.save()
                line_formset.save()
                messages.success(request, 'Đã lưu BOM.')
                return redirect(f"{request.path}?tab=bom&bom={bom.pk}")
            messages.error(request, 'Không lưu được BOM — kiểm tra lại các dòng.')
        elif action == 'save_process' and tab == 'process':
            step_formset = ProcessStepFormSet(request.POST, instance=bom, prefix='steps')
            if step_formset.is_valid():
                step_formset.save()
                messages.success(request, 'Đã lưu công đoạn.')
                return redirect(f"{request.path}?tab=process&bom={bom.pk}")
            messages.error(request, 'Không lưu được công đoạn — kiểm tra lại.')
        elif action == 'activate' and can_update:
            activate_bom(bom)
            messages.success(request, f'Đã kích hoạt BOM {bom.version_label}.')
            return redirect(f"{request.path}?tab={tab}&bom={bom.pk}")
        elif action == 'snapshot' and tab == 'costing':
            snap = save_costing_snapshot(bom, user=request.user)
            messages.success(request, f'Đã chốt costing: {snap.total_cost:,.0f} đ.')
            return redirect(f"{request.path}?tab=costing&bom={bom.pk}")

    if bom and can_update:
        if line_formset is None and tab == 'bom':
            meta_form = meta_form or BomVersionMetaForm(instance=bom)
            line_formset = BomLineFormSet(instance=bom, prefix='lines')
        if step_formset is None and tab == 'process':
            step_formset = ProcessStepFormSet(instance=bom, prefix='steps')

    return render(request, 'san_xuat/doc_detail.html', {
        'doc': doc,
        'tab': tab,
        'bom': bom,
        'versions': versions,
        'costing': costing,
        'snapshots': snapshots,
        'meta_form': meta_form,
        'line_formset': line_formset,
        'step_formset': step_formset,
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def product_code_search(request):
    q = (request.GET.get('q') or '').strip()
    return JsonResponse({'results': search_kv_products(q, limit=30)})
