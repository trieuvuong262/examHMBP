from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
import json

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
    ProductTechDocDescriptionForm,
    TechDocDesignUploadForm,
)
from san_xuat.models import BomVersion, ProductTechDoc, TechDocDesignFile
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
    from django.db.models import Count, Prefetch

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

    # Prefetch BOM versions kèm số dòng NPL và công đoạn
    bom_qs = BomVersion.objects.annotate(
        line_count=Count('lines', distinct=True),
        step_count=Count('process_steps', distinct=True),
    ).order_by('-created_at')
    qs = qs.prefetch_related(Prefetch('bom_versions', queryset=bom_qs))

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
    tab = (request.GET.get('tab') or 'info').strip().lower()
    if tab not in ('info', 'bom', 'process', 'costing', 'design', 'sku'):
        tab = 'info'

    bom = _get_bom_for_doc(doc, request.GET.get('bom'))
    versions = list(doc.bom_versions.order_by('-created_at'))
    costing = compute_costing(bom) if bom else None
    snapshots = list(bom.costing_snapshots.all()[:10]) if bom else []
    design_files = list(doc.design_files.select_related('uploaded_by').all())

    line_formset = None
    step_formset = None
    meta_form = None
    design_form = None
    desc_form = None
    can_update = user_can_update_module(request.user, MODULE_SAN_XUAT)

    if can_update and request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save_description':
            desc_form = ProductTechDocDescriptionForm(request.POST, instance=doc)
            if desc_form.is_valid():
                desc_form.save()
                messages.success(request, 'Đã lưu mô tả hồ sơ.')
                return redirect(f'{request.path}?tab=info')
            tab = 'info'
            messages.error(request, 'Không lưu được mô tả — kiểm tra lại.')
        elif action == 'upload_design':
            design_form = TechDocDesignUploadForm(request.POST, request.FILES)
            if design_form.is_valid():
                created = design_form.save(doc, user=request.user)
                messages.success(request, f'Đã tải lên {len(created)} tài liệu thiết kế.')
                return redirect(f'{request.path}?tab=design')
            tab = 'design'
            messages.error(request, 'Không tải lên được — kiểm tra lại tệp.')
        elif action == 'delete_design':
            file_id = request.POST.get('file_id')
            try:
                design_file = doc.design_files.get(pk=int(file_id))
            except (TypeError, ValueError, TechDocDesignFile.DoesNotExist):
                messages.error(request, 'Không tìm thấy tài liệu.')
            else:
                design_file.file.delete(save=False)
                design_file.delete()
                messages.success(request, 'Đã xóa tài liệu thiết kế.')
            return redirect(f'{request.path}?tab=design')
        elif bom and action == 'save_bom' and tab == 'bom':
            meta_form = BomVersionMetaForm(request.POST, instance=bom)
            line_formset = BomLineFormSet(request.POST, instance=bom, prefix='lines')
            if meta_form.is_valid() and line_formset.is_valid():
                meta_form.save()
                line_formset.save()
                messages.success(request, 'Đã lưu BOM.')
                return redirect(f"{request.path}?tab=bom&bom={bom.pk}")
            messages.error(request, 'Không lưu được BOM — kiểm tra lại các dòng.')
        elif bom and action == 'save_process' and tab == 'process':
            step_formset = ProcessStepFormSet(request.POST, instance=bom, prefix='steps')
            if step_formset.is_valid():
                step_formset.save()
                messages.success(request, 'Đã lưu công đoạn.')
                return redirect(f"{request.path}?tab=process&bom={bom.pk}")
            messages.error(request, 'Không lưu được công đoạn — kiểm tra lại.')
        elif bom and action == 'activate':
            activate_bom(bom)
            messages.success(request, f'Đã kích hoạt BOM {bom.version_label}.')
            return redirect(f"{request.path}?tab={tab}&bom={bom.pk}")
        elif bom and action == 'snapshot' and tab == 'costing':
            snap = save_costing_snapshot(bom, user=request.user)
            messages.success(request, f'Đã chốt costing: {snap.total_cost:,.0f} đ.')
            return redirect(f"{request.path}?tab=costing&bom={bom.pk}")
        elif action == 'expand_sku_matrix':
            from san_xuat.services.sku_catalog import SkuError, expand_style_matrix

            colors = request.POST.getlist('color_codes')
            sizes = request.POST.getlist('size_labels')
            try:
                rows = expand_style_matrix(
                    style_code=doc.product_code,
                    style_name=doc.product_name or '',
                    color_codes=colors,
                    size_labels=sizes,
                    user=request.user,
                )
            except SkuError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã sinh / cập nhật {len(rows)} SKU cho Style {doc.product_code}.')
            return redirect(f'{request.path}?tab=sku')
        elif action == 'add_single_sku':
            from san_xuat.services.sku_catalog import SkuError, get_or_create_sku

            try:
                sku = get_or_create_sku(
                    style_code=doc.product_code,
                    style_name=doc.product_name or '',
                    color_code=request.POST.get('color_code') or '',
                    size_label=request.POST.get('size_label') or '',
                    user=request.user,
                )
            except SkuError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã thêm SKU {sku.sku_code}.')
            return redirect(f'{request.path}?tab=sku')

    if can_update:
        if tab == 'info' and desc_form is None:
            desc_form = ProductTechDocDescriptionForm(instance=doc)
        if bom and line_formset is None and tab == 'bom':
            meta_form = meta_form or BomVersionMetaForm(instance=bom)
            line_formset = BomLineFormSet(instance=bom, prefix='lines')
        if bom and step_formset is None and tab == 'process':
            step_formset = ProcessStepFormSet(instance=bom, prefix='steps')
        if tab == 'design' and design_form is None:
            design_form = TechDocDesignUploadForm()

    from django.urls import reverse
    from django.db.models import Sum
    from hrm.module_permissions import MODULE_KHO_NPL, user_can_create_module
    from kho_npl.models import StockBalance
    from kho_npl.services.scrap_warehouse import exclude_scrap_locations

    issue_base_url = (
        reverse('kho_npl:issue_create')
        if user_can_create_module(request.user, MODULE_KHO_NPL)
        else None
    )
    issue_bom_url = None
    bom_stock_map = {}
    bom_stock_map_json = '{}'
    if bom and issue_base_url and any(line.material_id for line in bom.lines.all()):
        issue_bom_url = f'{issue_base_url}?bom={bom.pk}'
    if bom:
        import json
        from decimal import Decimal
        material_ids = [line.material_id for line in bom.lines.all() if line.material_id]
        if material_ids:
            for row in (
                exclude_scrap_locations(StockBalance.objects.filter(material_id__in=material_ids))
                .values('material_id')
                .annotate(total=Sum('quantity'))
            ):
                bom_stock_map[row['material_id']] = row['total'] or Decimal('0')
        for line in bom.lines.all():
            line.stock_qty = bom_stock_map.get(line.material_id, Decimal('0'))
        if line_formset is not None:
            for f in line_formset:
                mid = f.instance.material_id
                f.instance.stock_qty = bom_stock_map.get(mid, Decimal('0')) if mid else None
        bom_stock_map_json = json.dumps({
            str(k): float(v) for k, v in bom_stock_map.items()
        })

    from san_xuat.hub_models import SxColor, SxSize
    from san_xuat.services.sku_catalog import skus_for_style

    skus = list(skus_for_style(doc.product_code, active_only=False))
    colors = list(SxColor.objects.filter(is_active=True).order_by('sort_order', 'code'))
    sizes = list(SxSize.objects.filter(is_active=True).order_by('sort_order', 'code'))
    skus_active_count = sum(1 for s in skus if s.is_active)

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
        'design_form': design_form,
        'design_files': design_files,
        'desc_form': desc_form,
        'issue_base_url': issue_base_url,
        'issue_bom_url': issue_bom_url,
        'bom_stock_map': bom_stock_map,
        'bom_stock_map_json': bom_stock_map_json,
        'skus': skus,
        'skus_active_count': skus_active_count,
        'colors': colors,
        'sizes': sizes,
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def design_file_serve(request, pk):
    import mimetypes

    from san_xuat.design_nas_storage import design_file_abs_path, open_design_file

    design_file = get_object_or_404(
        TechDocDesignFile.objects.select_related('tech_doc'),
        pk=pk,
    )
    path = design_file_abs_path(design_file)
    if not path:
        raise Http404

    display_name = design_file.display_name or 'file'
    # Prefer real basename for Content-Disposition / MIME
    disk_name = path.name or display_name
    content_type = mimetypes.guess_type(disk_name)[0] or 'application/octet-stream'
    inline_types = {
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/bmp',
        'image/svg+xml',
    }
    force_download = (request.GET.get('download') or '').strip() in ('1', 'true', 'yes')
    as_attachment = force_download or content_type not in inline_types
    response = FileResponse(
        open_design_file(design_file),
        content_type=content_type,
        as_attachment=as_attachment,
        filename=disk_name,
    )
    return response


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def product_code_search(request):
    q = (request.GET.get('q') or '').strip()
    return JsonResponse({'results': search_kv_products(q, limit=30)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def process_catalog_search(request):
    """Gõ tìm công đoạn trong danh mục."""
    q = (request.GET.get('q') or '').strip()
    from san_xuat.models import SxProcessName

    qs = SxProcessName.objects.filter(is_active=True).order_by('sort_order', 'name')
    if q:
        qs = qs.filter(name__icontains=q)
    rows = [
        {'id': row.name, 'name': row.name, 'text': row.name}
        for row in qs[:40]
    ]
    return JsonResponse({'results': rows})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_POST
def process_catalog_add(request):
    """Thêm tên công đoạn vào danh mục dùng chung."""
    if not (
        user_can_update_module(request.user, MODULE_SAN_XUAT)
        or user_can_create_module(request.user, MODULE_SAN_XUAT)
    ):
        return JsonResponse({'error': 'Không có quyền thêm công đoạn.'}, status=403)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = request.POST
    name = (payload.get('name') if hasattr(payload, 'get') else '') or ''
    name = str(name).strip()
    if not name:
        return JsonResponse({'error': 'Nhập tên công đoạn.'}, status=400)
    from san_xuat.services.process_catalog import ensure_process_name

    try:
        row = ensure_process_name(name)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse({'name': row.name, 'id': row.pk})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def sku_search(request):
    from san_xuat.services.sku_catalog import search_skus

    q = (request.GET.get('q') or '').strip()
    style = (request.GET.get('style') or request.GET.get('style_code') or '').strip()
    try:
        limit = int(request.GET.get('limit') or 30)
    except (TypeError, ValueError):
        limit = 30
    return JsonResponse({'results': search_skus(q=q, style_code=style, limit=limit)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def sku_compose_preview(request):
    from san_xuat.services.sku_catalog import SkuError, compose_sku_code

    style = (request.GET.get('style') or request.GET.get('style_code') or '').strip()
    color = (request.GET.get('color') or request.GET.get('color_code') or '').strip()
    size = (request.GET.get('size') or request.GET.get('size_label') or '').strip()
    try:
        code = compose_sku_code(style_code=style, color_code=color, size_label=size)
    except SkuError as exc:
        return JsonResponse({'ok': False, 'error': str(exc), 'sku_code': ''}, status=400)
    return JsonResponse({'ok': True, 'sku_code': code})
