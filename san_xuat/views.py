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
    create_bom_version,
    create_tech_doc,
    get_working_bom,
)
from san_xuat.services.costing import compute_costing, save_costing_snapshot
from san_xuat.services.products import search_products


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
        elif bom and action == 'apply_routing' and tab == 'process':
            from san_xuat.ie_models import SxRouting
            from san_xuat.services.ie_ops import IeOpsError, apply_routing_to_bom

            rid = request.POST.get('routing_id')
            routing = None
            if rid and str(rid).isdigit():
                routing = SxRouting.objects.filter(pk=int(rid), is_active=True).first()
            if not routing:
                messages.error(request, 'Chưa chọn routing hợp lệ.')
            else:
                try:
                    result = apply_routing_to_bom(bom=bom, routing=routing, replace=True)
                except IeOpsError as exc:
                    messages.error(request, str(exc))
                else:
                    if result.linked_only:
                        messages.success(
                            request,
                            f'Đã gắn {result.routing_id} vào BOM (routing trống — giữ công đoạn hiện có).',
                        )
                    else:
                        messages.success(
                            request,
                            f'Đã áp {result.routing_id}: tạo {result.steps_created} công đoạn BOM.',
                        )
                    for w in result.warnings[:10]:
                        messages.warning(request, w)
            return redirect(f'{request.path}?tab=process&bom={bom.pk}')
        elif action == 'new_bom' and can_update:
            copy_flag = (request.POST.get('copy') or '').strip() in ('1', 'true', 'yes', 'on')
            copy_from = None
            if copy_flag:
                copy_from = bom or get_working_bom(doc)
            custom_label = (request.POST.get('version_label') or '').strip()
            try:
                new_bom = create_bom_version(
                    doc,
                    version_label=custom_label or None,
                    user=request.user,
                    copy_from=copy_from,
                )
            except BomError as exc:
                messages.error(request, str(exc))
                return redirect(f'{request.path}?tab=bom' + (f'&bom={bom.pk}' if bom else ''))
            messages.success(
                request,
                f'Đã tạo phiên bản BOM {new_bom.version_label}'
                + (' (sao chép từ bản trước).' if copy_from else '.'),
            )
            return redirect(f'{request.path}?tab=bom&bom={new_bom.pk}')
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
                messages.success(request, f'Đã tạo / cập nhật {len(rows)} SKU cho mã SX {doc.product_code}.')
            return redirect(f'{request.path}?tab=sku')
        elif action == 'delete_sku':
            from san_xuat.services.sku_catalog import SkuError, delete_sku

            try:
                deleted = delete_sku(
                    sku_id=request.POST.get('sku_id'),
                    style_code=doc.product_code,
                )
            except SkuError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã xóa SKU {deleted.sku_code}.')
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

    from django.db.models import Count, Q

    from san_xuat.hub_models import SxColor, SxSize
    from san_xuat.ie_models import SxRouting
    from san_xuat.services.sku_catalog import skus_for_style

    skus = list(skus_for_style(doc.product_code, active_only=False))
    colors = list(SxColor.objects.filter(is_active=True).order_by('sort_order', 'code'))
    sizes = list(SxSize.objects.filter(is_active=True).order_by('sort_order', 'code'))
    skus_active_count = sum(1 for s in skus if s.is_active)

    routing_choices = []
    if tab == 'process' and bom:
        routing_choices = list(
            SxRouting.objects.filter(is_active=True)
            .annotate(n_lines=Count('lines'))
            .filter(
                Q(style_code__iexact=doc.product_code)
                | Q(style_code__icontains=doc.product_code)
                | Q(tech_doc=doc)
            )
            .order_by('style_code', 'routing_rev')
        )
        # Nếu chưa khớp mã hàng, vẫn liệt kê routing active để IE chọn thủ công.
        if not routing_choices:
            routing_choices = list(
                SxRouting.objects.filter(is_active=True)
                .annotate(n_lines=Count('lines'))
                .order_by('style_code', 'routing_rev')[:80]
            )

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
        'routing_choices': routing_choices,
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
    return JsonResponse({'results': search_products(q, limit=30)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def mo_code_preview(request):
    """Xem trước mã LSX sẽ sinh theo mã SX."""
    product_code = (request.GET.get('product_code') or '').strip()
    if not product_code:
        return JsonResponse({'code': ''})
    from san_xuat.services.dispatch import _next_mo_code_for_product

    return JsonResponse({'code': _next_mo_code_for_product(product_code)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def mo_sku_matrix_api(request):
    """Ma trận màu × size theo mã SX (cho form tạo/sửa LSX)."""
    style = (request.GET.get('product_code') or request.GET.get('style') or '').strip()
    from san_xuat.services.dispatch import mo_sku_matrix

    return JsonResponse(mo_sku_matrix(style_code=style))


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def mo_bom_versions_api(request):
    """Danh sách phiên bản BOM ngang hàng theo mã SX."""
    product_code = (request.GET.get('product_code') or '').strip()
    from san_xuat.models import ProductTechDoc

    results = []
    if product_code:
        doc = ProductTechDoc.objects.filter(product_code__iexact=product_code).first()
        if doc:
            for bom in doc.bom_versions.order_by('created_at', 'id'):
                note = (bom.notes or '').strip()
                results.append({
                    'id': bom.pk,
                    'label': bom.version_label,
                    'text': f'{bom.version_label}' + (f' — {note[:40]}' if note else ''),
                    'notes': note,
                })
    return JsonResponse({'results': results})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def process_catalog_search(request):
    """Gõ tìm công đoạn chuẩn trong thư viện IE."""
    q = (request.GET.get('q') or '').strip()
    from san_xuat.services.process_catalog import process_catalog_choices

    rows = []
    for value, label in process_catalog_choices(extra_value='', blank_label='')[:200]:
        name = (value or '').strip()
        if not name:
            continue
        if q and q.casefold() not in name.casefold():
            continue
        rows.append({'id': name, 'name': name, 'text': name})
        if len(rows) >= 40:
            break
    return JsonResponse({'results': rows})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_POST
def routing_create_api(request):
    """Tạo routing trống thủ công (không cần Excel)."""
    if not (
        user_can_update_module(request.user, MODULE_SAN_XUAT)
        or user_can_create_module(request.user, MODULE_SAN_XUAT)
    ):
        return JsonResponse({'error': 'Không có quyền tạo routing.'}, status=403)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = request.POST

    get = payload.get if hasattr(payload, 'get') else lambda *_: ''
    label = str(get('label') or get('style_code') or get('routing_id') or '').strip()
    tech_doc = None
    doc_id = get('tech_doc_id')
    if doc_id and str(doc_id).isdigit():
        tech_doc = ProductTechDoc.objects.filter(pk=int(doc_id)).first()

    from san_xuat.services.ie_ops import IeOpsError, create_blank_routing

    try:
        routing = create_blank_routing(
            style_code=label,
            routing_id=label,
            style_name=str(get('style_name') or (tech_doc.product_name if tech_doc else '') or ''),
            tech_doc=tech_doc,
            user=request.user,
        )
    except IeOpsError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    text = f'{routing.style_code} · {routing.routing_rev} — {routing.routing_id} (0 CĐ)'
    return JsonResponse({
        'id': routing.pk,
        'value': str(routing.pk),
        'text': text,
        'routing_id': routing.routing_id,
        'style_code': routing.style_code,
        'routing_rev': routing.routing_rev,
    })


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
