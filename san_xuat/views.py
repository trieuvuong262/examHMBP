from django.contrib import messages
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST
import json

from assessment.decorators import module_perm_required
from hrm.module_permissions import (
    MODULE_SAN_XUAT,
    user_can_create_module,
    user_can_delete_module,
    user_can_export_module,
    user_can_print_module,
    user_can_update_module,
)
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from san_xuat.forms import (
    BomLineFormSet,
    BomOverheadAmountForm,
    BomVersionMetaForm,
    ProductTechDocCreateForm,
    ProductTechDocDescriptionForm,
    TechDocDesignUploadForm,
    TechDocGalleryUploadForm,
)
from san_xuat.models import BomVersion, ProductTechDoc, TechDocDesignFile
from san_xuat.services.bom import (
    BomError,
    create_bom_version,
    create_tech_doc,
    get_working_bom,
)
from san_xuat.services.costing import compute_costing, save_costing_snapshot
from san_xuat.services.dispatch import fg_receipt_prefill
from san_xuat.services.products import search_gc_out_items, search_products
from hrm.user_search import search_issue_recipients


def _perm_ctx(request):
    can_create = user_can_create_module(request.user, MODULE_SAN_XUAT)
    can_update = user_can_update_module(request.user, MODULE_SAN_XUAT)
    can_delete = user_can_delete_module(request.user, MODULE_SAN_XUAT)
    return {
        'can_create': can_create,
        'can_update': can_update,
        'can_delete': can_delete,
        'can_pick_rows': bool(can_update or can_delete),
        'can_print': user_can_print_module(request.user, MODULE_SAN_XUAT),
        'can_export': user_can_export_module(request.user, MODULE_SAN_XUAT),
    }


def _parse_int_pks(raw_values) -> list[int]:
    pks: list[int] = []
    seen: set[int] = set()
    for raw in raw_values or []:
        s = str(raw or '').strip()
        if not s.isdigit():
            continue
        pk = int(s)
        if pk in seen:
            continue
        seen.add(pk)
        pks.append(pk)
    return pks


def _bulk_delete_tech_docs(*, request, perms: dict, pks: list[int]) -> None:
    if not perms.get('can_pick_rows'):
        messages.error(request, 'Bạn không có quyền xóa hồ sơ.')
        return
    if not pks:
        messages.error(request, 'Chưa chọn hồ sơ nào.')
        return
    deleted = 0
    errors: list[str] = []
    for doc in ProductTechDoc.objects.filter(pk__in=pks):
        label = doc.product_code or str(doc.pk)
        try:
            doc.delete()
            deleted += 1
        except ProtectedError:
            errors.append(f'{label}: đang được tham chiếu, không xóa được')
        except Exception as exc:
            errors.append(f'{label}: {exc}')
    if deleted:
        messages.success(request, f'Đã xóa {deleted} hồ sơ thiết kế.')
    if errors:
        messages.error(request, '; '.join(errors[:5]))
    if not deleted and not errors:
        messages.error(request, 'Không xóa được hồ sơ đã chọn.')


def _doc_list_back_query(request) -> str:
    """Giữ bộ lọc danh sách hồ sơ khi vào chi tiết rồi bấm Quay lại."""
    params = request.GET.copy()
    for key in ('tab', 'bom', 'routing', 'action'):
        params.pop(key, None)
    return params.urlencode()[:2000]


def _doc_tab_redirect(request, tab: str, *, bom=None, routing=None):
    bits = [f'tab={tab}']
    if bom is not None:
        bits.append(f'bom={bom}')
    if routing is not None:
        bits.append(f'routing={routing}')
    extra = _doc_list_back_query(request)
    if extra:
        bits.append(extra)
    return redirect(f'{request.path}?{"&".join(bits)}')


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
    from san_xuat.services.products import fill_tech_doc_display_images

    perms = _perm_ctx(request)
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        back = request.get_full_path() if request.GET else reverse('san_xuat:doc_list')
        if action == 'bulk_delete_doc':
            _bulk_delete_tech_docs(
                request=request,
                perms=perms,
                pks=_parse_int_pks(request.POST.getlist('pk')),
            )
        else:
            messages.error(request, 'Hành động không hợp lệ.')
        return redirect(back)

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
    from san_xuat.ie_models import SxRouting

    routing_qs = SxRouting.objects.annotate(
        n_lines=Count('lines', distinct=True),
    ).order_by('routing_rev', 'pk')
    gallery_qs = TechDocDesignFile.objects.filter(
        purpose=TechDocDesignFile.PURPOSE_GALLERY,
    ).order_by('sort_order', 'uploaded_at', 'pk')
    qs = qs.prefetch_related(
        Prefetch('bom_versions', queryset=bom_qs),
        Prefetch('routings', queryset=routing_qs),
        Prefetch('design_files', queryset=gallery_qs, to_attr='gallery_images'),
    )

    page_obj, query_string = paginate_queryset(request, qs, per_page=500)
    page_obj.object_list = list(page_obj.object_list)
    fill_tech_doc_display_images(page_obj.object_list)
    return render(request, 'san_xuat/doc_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'total_count': ProductTechDoc.objects.count(),
        'hide_sx_date_filter': True,
        **sx_filter_context(filters),
        **sx_list_grid_context(request, 'doc_list'),
        **perms,
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
                messages.success(
                    request,
                    f'Đã tạo hồ sơ SX {doc.product_name or doc.product_code}.',
                )
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
            return doc.bom_versions.prefetch_related(
                'lines__material__unit',
                'lines__material__color',
                'lines__material__specification',
                'process_steps',
            ).get(pk=int(bom_id))
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
    if bom:
        # Prefetch bộ phận trên từng công đoạn
        bom = (
            BomVersion.objects.filter(pk=bom.pk)
            .prefetch_related(
                'lines__material__unit',
                'lines__material__color',
                'lines__material__specification',
                'process_steps__work_center',
            )
            .select_related('routing')
            .first()
        )
    versions = list(doc.bom_versions.order_by('-created_at'))
    costing = None
    costing_routing_preview = False
    snapshots = list(bom.costing_snapshots.all()[:10]) if bom else []
    all_files = list(doc.design_files.select_related('uploaded_by').all())
    design_files = [f for f in all_files if f.purpose != TechDocDesignFile.PURPOSE_GALLERY]
    gallery_images = sorted(
        [f for f in all_files if f.purpose == TechDocDesignFile.PURPOSE_GALLERY],
        key=lambda f: (f.sort_order, f.uploaded_at, f.pk),
    )
    gallery_urls = [f.file_url for f in gallery_images if f.is_image and f.file_url]

    line_formset = None
    meta_form = None
    overhead_form = None
    design_form = None
    gallery_form = None
    desc_form = None
    can_update = user_can_update_module(request.user, MODULE_SAN_XUAT)

    if can_update and request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save_description':
            desc_form = ProductTechDocDescriptionForm(request.POST, instance=doc)
            if desc_form.is_valid():
                desc_form.save()
                messages.success(request, 'Đã lưu mô tả hồ sơ.')
                return _doc_tab_redirect(request, 'info')
            tab = 'info'
            desc_form._show_edit = True
            messages.error(request, 'Không lưu được mô tả — kiểm tra lại.')
        elif action == 'upload_gallery':
            gallery_form = TechDocGalleryUploadForm(request.POST, request.FILES)
            if gallery_form.is_valid():
                created = gallery_form.save(doc, user=request.user)
                messages.success(request, f'Đã tải lên {len(created)} ảnh.')
                return _doc_tab_redirect(request, 'info')
            tab = 'info'
            messages.error(request, 'Không tải lên được ảnh.')
        elif action == 'reorder_gallery':
            raw_ids = [part.strip() for part in (request.POST.get('ids') or '').split(',') if part.strip()]
            ids = []
            for part in raw_ids:
                if not part.isdigit():
                    ids = []
                    break
                ids.append(int(part))
            files = {
                f.pk: f
                for f in doc.design_files.filter(
                    purpose=TechDocDesignFile.PURPOSE_GALLERY,
                    pk__in=ids,
                )
            }
            ok = ids and len(files) == len(ids) and all(pk in files for pk in ids)
            if ok:
                for order, pk in enumerate(ids, start=1):
                    item = files[pk]
                    if item.sort_order != order:
                        item.sort_order = order
                        item.save(update_fields=['sort_order'])
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'ok': bool(ok)})
            if ok:
                messages.success(request, 'Đã sắp xếp gallery.')
            else:
                messages.error(request, 'Không sắp xếp được gallery.')
            return _doc_tab_redirect(request, 'info')
        elif action == 'delete_gallery':
            file_id = request.POST.get('file_id')
            try:
                gallery_file = doc.design_files.get(
                    pk=int(file_id),
                    purpose=TechDocDesignFile.PURPOSE_GALLERY,
                )
            except (TypeError, ValueError, TechDocDesignFile.DoesNotExist):
                messages.error(request, 'Không tìm thấy ảnh.')
            else:
                gallery_file.file.delete(save=False)
                gallery_file.delete()
                messages.success(request, 'Đã xóa ảnh.')
            return _doc_tab_redirect(request, 'info')
        elif action == 'upload_design':
            design_form = TechDocDesignUploadForm(request.POST, request.FILES)
            if design_form.is_valid():
                created = design_form.save(doc, user=request.user)
                messages.success(request, f'Đã tải lên {len(created)} tài liệu thiết kế.')
                return _doc_tab_redirect(request, 'design')
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
            return _doc_tab_redirect(request, 'design')
        elif bom and action == 'save_bom' and tab == 'bom':
            meta_form = BomVersionMetaForm(request.POST, instance=bom)
            line_formset = BomLineFormSet(request.POST, instance=bom, prefix='lines')
            if meta_form.is_valid() and line_formset.is_valid():
                meta_form.save()
                line_formset.save()
                messages.success(request, 'Đã lưu BOM.')
                return _doc_tab_redirect(request, 'bom', bom=bom.pk)
            messages.error(request, 'Không lưu được BOM — kiểm tra lại các dòng.')
        elif action == 'add_doc_routing_line' and tab == 'process':
            from decimal import Decimal

            from san_xuat.ie_models import SxRouting
            from san_xuat.models import ProcessStep
            from san_xuat.services.ie_ops import (
                IeOpsError,
                create_blank_routing,
                delete_routing_line,
                norm_per_hour_from_smv_seconds,
                upsert_routing_line,
            )

            routing_id = (request.POST.get('routing_id') or '').strip()
            routing = (
                SxRouting.objects.filter(
                    Q(tech_doc=doc) | Q(bom_versions__tech_doc=doc),
                    pk=int(routing_id),
                ).distinct().first()
                if routing_id.isdigit() else None
            )
            group_code = (request.POST.get('group_code') or '').strip()
            op_code = (request.POST.get('op_code') or '').strip()
            op_rev = (request.POST.get('op_rev') or 'R01').strip() or 'R01'
            op_name = (request.POST.get('op_name_vi') or '').strip()
            work_center_code = (request.POST.get('work_center_code') or '').strip()
            if not group_code or not op_name:
                messages.error(request, 'Chọn nhóm và công đoạn từ thư viện.')
            else:
                try:
                    if routing is None:
                        routing = create_blank_routing(tech_doc=doc, user=request.user)
                    line = upsert_routing_line(
                        routing=routing,
                        seq_no=None,
                        op_code=op_code,
                        op_rev=op_rev,
                        op_name_vi=op_name,
                        group_code=group_code,
                        work_center_code=work_center_code,
                        library_unit_smv=None,
                        applied_unit_smv=Decimal('0'),
                        price_factor=Decimal('0'),
                        copy_library_to_applied=False,
                    )
                    smv = line.library_unit_smv or Decimal('0')
                    if smv <= 0:
                        delete_routing_line(routing=routing, line_pk=line.pk)
                        raise IeOpsError(
                            f'Công đoạn {op_code} chưa có SMV chuẩn trong thư viện — cập nhật IE trước.'
                        )
                    norm = norm_per_hour_from_smv_seconds(smv)
                    if bom:
                        step, _ = ProcessStep.objects.update_or_create(
                            bom=bom,
                            routing_line=line,
                            defaults={
                                'sequence': line.seq_no or 10,
                                'process_name': (line.op_name_vi or line.op_code or '')[:120],
                                'operation': line.operation,
                                'op_code': (line.op_code or '')[:30],
                                'norm_per_hour': max(norm, Decimal('0.01')),
                                'cost_per_hour': Decimal('0'),
                                'std_time_minutes': (smv / Decimal('60')).quantize(Decimal('0.01')),
                                'work_center': line.work_center,
                                'notes': f'Routing {routing.routing_id}'[:255],
                            },
                        )
                        if bom.routing_id != routing.pk:
                            bom.routing = routing
                            bom.save(update_fields=['routing', 'updated_at'])
                except IeOpsError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, 'Đã thêm công đoạn vào routing.')
            return _doc_tab_redirect(
                request,
                'process',
                bom=bom.pk if bom else None,
                routing=routing.pk if routing else None,
            )
        elif action == 'delete_doc_routing_line' and tab == 'process':
            from san_xuat.ie_models import SxRouting
            from san_xuat.models import ProcessStep
            from san_xuat.services.ie_ops import IeOpsError, delete_routing_line

            routing_id = (request.POST.get('routing_id') or '').strip()
            line_id = (request.POST.get('line_id') or '').strip()
            routing = (
                SxRouting.objects.filter(
                    Q(tech_doc=doc) | Q(bom_versions__tech_doc=doc),
                    pk=int(routing_id),
                ).distinct().first()
                if routing_id.isdigit() else None
            )
            try:
                if not routing or not line_id.isdigit():
                    raise IeOpsError('Không tìm thấy dòng routing.')
                ProcessStep.objects.filter(bom__tech_doc=doc, routing_line_id=int(line_id)).delete()
                delete_routing_line(routing=routing, line_pk=int(line_id))
            except IeOpsError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, 'Đã xóa công đoạn khỏi routing.')
            return _doc_tab_redirect(
                request, 'process', bom=bom.pk if bom else None, routing=routing_id or None,
            )
        elif action == 'create_doc_routing' and can_update:
            from san_xuat.services.ie_ops import IeOpsError, create_blank_routing

            preferred = (request.POST.get('routing_rev') or '').strip().upper().replace(' ', '')
            seed = (doc.product_code or '').strip()
            if preferred:
                if preferred.startswith('R') and preferred[1:].isdigit():
                    seed = f'{doc.product_code}-{preferred}'
                elif preferred.isdigit():
                    seed = f'{doc.product_code}-R{int(preferred):02d}'
            try:
                routing = create_blank_routing(
                    tech_doc=doc,
                    style_code=seed,
                    user=request.user,
                )
            except IeOpsError as exc:
                messages.error(request, str(exc))
                return _doc_tab_redirect(
                    request, 'process', bom=bom.pk if bom else None,
                )
            messages.success(request, f'Đã tạo phiên bản routing {routing.routing_rev}.')
            return _doc_tab_redirect(
                request, 'process', bom=bom.pk if bom else None, routing=routing.pk,
            )
        elif action == 'clone_doc_routing' and can_update:
            from san_xuat.ie_models import SxRouting
            from san_xuat.services.ie_ops import IeOpsError, clone_routing_revision

            routing_id = (request.POST.get('routing_id') or '').strip()
            source = (
                SxRouting.objects.filter(
                    Q(tech_doc=doc) | Q(bom_versions__tech_doc=doc),
                    pk=int(routing_id),
                ).distinct().first()
                if routing_id.isdigit() else None
            )
            if source is None:
                messages.error(request, 'Chọn phiên bản routing để sao chép.')
                return _doc_tab_redirect(
                    request, 'process', bom=bom.pk if bom else None,
                )
            try:
                clone = clone_routing_revision(routing=source, user=request.user)
                if clone.tech_doc_id != doc.pk:
                    clone.tech_doc = doc
                    clone.save(update_fields=['tech_doc', 'updated_at'])
            except IeOpsError as exc:
                messages.error(request, str(exc))
                return _doc_tab_redirect(
                    request, 'process', bom=bom.pk if bom else None, routing=source.pk,
                )
            messages.success(
                request,
                f'Đã tạo phiên bản routing {clone.routing_rev} (sao chép từ {source.routing_rev}).',
            )
            return _doc_tab_redirect(
                request, 'process', bom=bom.pk if bom else None, routing=clone.pk,
            )
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
                return _doc_tab_redirect(request, 'bom', bom=bom.pk if bom else None)
            messages.success(
                request,
                f'Đã tạo phiên bản BOM {new_bom.version_label}'
                + (' (sao chép từ bản trước).' if copy_from else '.'),
            )
            return _doc_tab_redirect(request, 'bom', bom=new_bom.pk)
        elif bom and action == 'apply_doc_routing' and can_update:
            from decimal import Decimal

            from san_xuat.ie_models import SxRouting
            from san_xuat.models import ProcessStep
            from san_xuat.services.ie_ops import (
                IeOpsError,
                norm_per_hour_from_smv_seconds,
                routing_line_smv_seconds,
            )

            routing_id = (request.POST.get('routing_id') or '').strip()
            routing = (
                SxRouting.objects.filter(
                    Q(tech_doc=doc) | Q(bom_versions__tech_doc=doc),
                    pk=int(routing_id),
                ).distinct().first()
                if routing_id.isdigit() else None
            )
            if routing is None:
                messages.error(request, 'Chọn phiên bản routing để gắn vào BOM.')
                return _doc_tab_redirect(request, 'costing', bom=bom.pk)
            try:
                bom.routing = routing
                bom.save(update_fields=['routing', 'updated_at'])
                bom.process_steps.all().delete()
                for line in routing.lines.select_related('operation', 'work_center').order_by('seq_no', 'pk'):
                    smv = routing_line_smv_seconds(line)
                    norm = norm_per_hour_from_smv_seconds(smv)
                    if norm <= 0:
                        norm = Decimal('0.01')
                    ProcessStep.objects.create(
                        bom=bom,
                        sequence=line.seq_no or 10,
                        process_name=(line.op_name_vi or line.op_code or '')[:120],
                        operation=line.operation,
                        op_code=(line.op_code or '')[:30],
                        routing_line=line,
                        norm_per_hour=norm,
                        cost_per_hour=line.price_factor or Decimal('0'),
                        std_time_minutes=(smv / Decimal('60')).quantize(Decimal('0.01')) if smv > 0 else Decimal('0'),
                        work_center=line.work_center,
                        notes=f'Routing {routing.routing_id}'[:255],
                    )
            except IeOpsError as exc:
                messages.error(request, str(exc))
                return _doc_tab_redirect(
                    request, 'costing', bom=bom.pk, routing=routing.pk,
                )
            messages.success(
                request,
                f'Đã gắn routing {routing.routing_rev} vào BOM {bom.version_label} — costing cập nhật theo cặp này.',
            )
            return _doc_tab_redirect(
                request, 'costing', bom=bom.pk, routing=routing.pk,
            )
        elif bom and action == 'save_overhead' and tab == 'costing':
            overhead_form = BomOverheadAmountForm(request.POST, instance=bom)
            if overhead_form.is_valid():
                overhead_form.save()
                messages.success(request, 'Đã lưu chi phí sản xuất chung.')
                return _doc_tab_redirect(
                    request, 'costing', bom=bom.pk,
                    routing=request.POST.get('routing_id') or None,
                )
            messages.error(request, 'Không lưu được chi phí sản xuất chung — kiểm tra lại số tiền.')
        elif bom and action == 'snapshot' and tab == 'costing':
            snap = save_costing_snapshot(bom, user=request.user)
            messages.success(request, f'Đã chốt costing: {snap.total_cost:,.0f} đ.')
            return _doc_tab_redirect(
                request, 'costing', bom=bom.pk,
                routing=request.POST.get('routing_id') or (bom.routing_id or None),
            )

    edit_info = can_update and (
        bool(request.GET.get('edit_info')) or getattr(desc_form, '_show_edit', False)
    )

    if can_update:
        if edit_info and desc_form is None:
            desc_form = ProductTechDocDescriptionForm(instance=doc)
        if bom and line_formset is None and tab == 'bom':
            meta_form = meta_form or BomVersionMetaForm(instance=bom)
            line_formset = BomLineFormSet(instance=bom, prefix='lines')
        if bom and overhead_form is None and tab == 'costing':
            overhead_form = BomOverheadAmountForm(instance=bom)
        if tab == 'design' and design_form is None:
            design_form = TechDocDesignUploadForm()
        if tab == 'info' and gallery_form is None:
            gallery_form = TechDocGalleryUploadForm()

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

    from san_xuat.ie_models import SxRouting

    skus = []
    skus_active_count = 0
    sku_color_count = 0
    sku_size_count = 0
    catalog_category = ''
    catalog_unit = ''
    catalog_colors = []
    catalog_sizes = []
    if tab in ('sku', 'info'):
        from kho_san_pham.models import Product

        code = (doc.product_code or '').strip()
        catalog = list(
            Product.objects.filter(Q(style_code__iexact=code) | Q(code__iexact=code))
            .order_by('color_code', 'size_label', 'code')
        )
        by_style = [
            p for p in catalog
            if (p.style_code or '').strip().upper() == code.upper()
        ]
        skus = by_style or catalog
        skus_active_count = sum(1 for p in skus if p.is_active)
        sku_color_count = len({
            (p.color_code or '').strip().upper()
            for p in skus
            if (p.color_code or '').strip()
        })
        sku_size_count = len({
            (p.size_label or '').strip().upper()
            for p in skus
            if (p.size_label or '').strip()
        })
        seen_colors, seen_sizes = [], []
        for p in skus:
            color = (p.color_label or p.color_code or '').strip()
            size = (p.size_label or '').strip()
            if color and color not in seen_colors:
                seen_colors.append(color)
            if size and size not in seen_sizes:
                seen_sizes.append(size)
            if not catalog_category and (p.category_name or '').strip():
                catalog_category = p.category_name.strip()
            if not catalog_unit and (p.unit or '').strip():
                catalog_unit = p.unit.strip()
        catalog_colors = seen_colors
        catalog_sizes = seen_sizes

    process_routings = []
    process_routing = None
    routing_lines = []
    operation_groups = []
    work_centers = []
    from san_xuat.ie_models import SxOperationGroup, SxRouting
    from san_xuat.services.capacity_from_hrm import hr_work_centers_qs

    process_routings = list(
        SxRouting.objects.filter(
            Q(tech_doc=doc) | Q(bom_versions__tech_doc=doc)
        ).distinct().annotate(n_lines=Count('lines', distinct=True)).order_by('routing_rev', 'pk')
    )
    requested_routing = (request.GET.get('routing') or '').strip()
    if requested_routing.isdigit():
        process_routing = next(
            (item for item in process_routings if item.pk == int(requested_routing)),
            None,
        )
    if process_routing is None and bom and bom.routing_id:
        process_routing = next(
            (item for item in process_routings if item.pk == bom.routing_id),
            None,
        )
    if process_routing is None and process_routings:
        process_routing = process_routings[-1]

    if bom:
        if tab == 'costing' and process_routing is not None:
            costing = compute_costing(bom, routing=process_routing)
            costing_routing_preview = bom.routing_id != process_routing.pk
        else:
            costing = compute_costing(bom)
            costing_routing_preview = False

    if tab == 'process':
        if process_routing:
            routing_lines = list(
                process_routing.lines.select_related('work_center').order_by('seq_no', 'pk')
            )
            group_names = {
                (g.code or '').casefold(): g.name
                for g in SxOperationGroup.objects.filter(
                    code__in=[ln.group_code for ln in routing_lines if ln.group_code]
                )
            }
            for line in routing_lines:
                line.display_group_name = group_names.get((line.group_code or '').casefold(), '')
        operation_groups = list(
            SxOperationGroup.objects.filter(is_active=True).order_by('sort_order', 'code')
        )
        work_centers = list(hr_work_centers_qs())

    from san_xuat.services.products import fill_tech_doc_display_images
    from tools.services import office_preview_available

    doc.gallery_images = gallery_images
    fill_tech_doc_display_images([doc])
    office_preview_ready = office_preview_available()

    return render(request, 'san_xuat/doc_detail.html', {
        'doc': doc,
        'tab': tab,
        'bom': bom,
        'versions': versions,
        'costing': costing,
        'snapshots': snapshots,
        'meta_form': meta_form,
        'overhead_form': overhead_form,
        'line_formset': line_formset,
        'design_form': design_form,
        'design_files': design_files,
        'gallery_form': gallery_form,
        'gallery_images': gallery_images,
        'gallery_urls_json': json.dumps(gallery_urls),
        'desc_form': desc_form,
        'issue_base_url': issue_base_url,
        'issue_bom_url': issue_bom_url,
        'bom_stock_map': bom_stock_map,
        'bom_stock_map_json': bom_stock_map_json,
        'skus': skus,
        'skus_active_count': skus_active_count,
        'catalog_category': catalog_category,
        'catalog_unit': catalog_unit,
        'catalog_colors': catalog_colors,
        'catalog_sizes': catalog_sizes,
        'sku_color_count': sku_color_count,
        'sku_size_count': sku_size_count,
        'process_routings': process_routings,
        'process_routing': process_routing,
        'routing_lines': routing_lines,
        'operation_groups': operation_groups,
        'work_centers': work_centers,
        'costing_routing_preview': costing_routing_preview,
        'office_preview_ready': office_preview_ready,
        'edit_info': edit_info,
        'list_back_query': _doc_list_back_query(request),
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
@xframe_options_sameorigin
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
    if not force_download and (design_file.is_ai or design_file.is_pdf):
        try:
            with path.open('rb') as fh:
                head = fh.read(8)
        except OSError:
            head = b''
        if head.startswith(b'%PDF'):
            content_type = 'application/pdf'
            inline_types.add('application/pdf')
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
@xframe_options_sameorigin
def design_file_preview(request, pk):
    """Xem trước PDF / Word / Excel / AI (PDF-compatible) trong iframe."""
    from nas_storage.file_preview import preview_unavailable_html, serve_preview_response
    from san_xuat.design_nas_storage import design_file_abs_path

    design_file = get_object_or_404(
        TechDocDesignFile.objects.select_related('tech_doc'),
        pk=pk,
    )
    path = design_file_abs_path(design_file)
    if not path:
        raise Http404
    ext = path.suffix.lower()
    try:
        with path.open('rb') as fh:
            head = fh.read(8)
    except OSError:
        raise Http404
    if ext == '.pdf' or (ext == '.ai' and head.startswith(b'%PDF')):
        return serve_preview_response(path, design_file.display_name, ext='.pdf')
    if ext == '.ai':
        return preview_unavailable_html(
            'File AI này không xem trước được trên trình duyệt. Hãy tải về Adobe Illustrator.'
        )
    return serve_preview_response(path, design_file.display_name, ext=ext)


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def product_code_search(request):
    q = (request.GET.get('q') or '').strip()
    return JsonResponse({'results': search_products(q, limit=30)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def gc_out_item_search(request):
    """TomSelect dòng xuất GC: NPL + BTP/SP."""
    q = (request.GET.get('q') or '').strip()
    return JsonResponse({'results': search_gc_out_items(q, limit=40)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def employee_search(request):
    """TomSelect người nhập / nhân viên HR."""
    q = (request.GET.get('q') or '').strip()
    limit = 1000 if not q else 50
    return JsonResponse({'results': search_issue_recipients(q, limit=limit)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def customer_search(request):
    """TomSelect: khách hàng từ mirror KiotViet (kv_customer)."""
    q = (request.GET.get('q') or '').strip()
    from kiotviet.local_lookup import search_customers

    return JsonResponse({'results': search_customers(q, limit=30)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def sales_order_line_versions_api(request):
    """BOM + routing theo mã SP — dùng dropdown dòng đơn đặt hàng."""
    from django.urls import reverse

    from decimal import Decimal

    from san_xuat.ie_models import SxRouting
    from san_xuat.models import ProductTechDoc
    from san_xuat.services.order_routing import (
        default_routing_for_product,
        process_preview_from_bom,
        process_preview_from_routing,
        smv_from_process_step,
    )

    from urllib.parse import urlencode

    product_code = (request.GET.get('product_code') or '').strip()
    routing_qs = {}
    if product_code:
        routing_qs['style_code'] = product_code
    payload = {
        'product_code': product_code,
        'tech_doc_id': None,
        'doc_url': '',
        'create_url': reverse('san_xuat:doc_create') + (
            f'?code={product_code}' if product_code else ''
        ),
        'routing_create_url': reverse('san_xuat:ie_routing_create') + '?' + urlencode(routing_qs),
        'bom_versions': [],
        'routings': [],
        'default_routing_id': None,
        'default_bom_id': None,
        'steps': [],
        'steps_source': '',
        'bom_lines': [],
    }
    if not product_code:
        return JsonResponse(payload)

    doc = ProductTechDoc.objects.filter(product_code__iexact=product_code).first()
    if doc:
        payload['tech_doc_id'] = doc.pk
        payload['doc_url'] = reverse('san_xuat:doc_detail', kwargs={'pk': doc.pk})
        if (doc.product_name or '').strip():
            routing_qs['style_name'] = doc.product_name.strip()
            payload['routing_create_url'] = (
                reverse('san_xuat:ie_routing_create') + '?' + urlencode(routing_qs)
            )
        boms = list(
            doc.bom_versions.prefetch_related(
                'process_steps',
                'lines__material__unit',
            ).order_by('created_at', 'id')
        )
        if boms:
            with_steps = [b for b in boms if b.process_steps.all()]
            payload['default_bom_id'] = (with_steps or boms)[-1].pk
        for bom in boms:
            label = bom.version_label or f'#{bom.pk}'
            note = (bom.notes or '').strip()
            steps = list(bom.process_steps.all())
            total_smv = sum((smv_from_process_step(s) for s in steps), Decimal('0'))
            text = label
            if note:
                text = f'{label} — {note[:40]}'
            payload['bom_versions'].append({
                'id': bom.pk,
                'text': text,
                'label': label,
                'step_count': len(steps),
                'line_count': bom.lines.count() if hasattr(bom, 'lines') else 0,
                'total_smv': str(total_smv.quantize(Decimal('0.01'))),
            })
        routings = SxRouting.objects.filter(
            Q(style_code__iexact=product_code)
            | Q(tech_doc_id=doc.pk)
            | Q(bom_versions__tech_doc_id=doc.pk)
        ).distinct().order_by('routing_rev', 'id')
    else:
        routings = SxRouting.objects.filter(style_code__iexact=product_code).order_by(
            'routing_rev', 'id',
        )

    for rt in routings:
        rev = (rt.routing_rev or '').strip() or f'#{rt.pk}'
        status = rt.get_approval_status_display() if hasattr(rt, 'get_approval_status_display') else ''
        text = f'{rev}'
        if status:
            text = f'{rev} · {status}'
        payload['routings'].append({'id': rt.pk, 'text': text, 'label': rev})

    default_rt = default_routing_for_product(product_code)
    if default_rt:
        payload['default_routing_id'] = default_rt.pk

    preview_rt_id = (request.GET.get('routing_id') or '').strip()
    preview_bom_id = (request.GET.get('bom_version_id') or '').strip()
    steps = []
    source = ''
    bom_for_lines = None
    if preview_bom_id.isdigit():
        from san_xuat.models import BomVersion

        bom_for_lines = BomVersion.objects.filter(pk=int(preview_bom_id)).first()
    elif payload.get('default_bom_id'):
        from san_xuat.models import BomVersion

        bom_for_lines = BomVersion.objects.filter(pk=payload['default_bom_id']).first()

    if preview_rt_id.isdigit():
        rt = SxRouting.objects.filter(pk=int(preview_rt_id)).first()
        if rt:
            steps = process_preview_from_routing(rt)
            source = 'ie'
    if not steps and bom_for_lines is not None:
        steps = process_preview_from_bom(bom_for_lines)
        source = 'bom'
    if not steps and default_rt:
        steps = process_preview_from_routing(default_rt)
        source = 'ie'
    payload['steps'] = steps
    payload['steps_source'] = source

    if bom_for_lines is not None:
        from san_xuat.services.sales_orders import bom_lines_snapshot

        payload['bom_lines'] = bom_lines_snapshot(bom_for_lines.pk)

    return JsonResponse(payload)


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def suggest_qty_stock_api(request):
    """Tồn + tốc độ tiêu thụ (bán KV N ngày) theo size — công cụ đề xuất SL."""
    style = (request.GET.get('style') or request.GET.get('product_code') or '').strip()
    try:
        days = int(request.GET.get('days') or 30)
    except (TypeError, ValueError):
        days = 30
    from san_xuat.services.products import suggest_style_size_stock

    return JsonResponse(suggest_style_size_stock(style, days=days))


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
def mo_fg_receipt_source_api(request):
    """Nguồn form yêu cầu nhập thành phẩm theo lệnh sản xuất."""
    from san_xuat.hub_models import SxProductionOrder, SxProductionStat

    mo_id = (request.GET.get('mo') or request.GET.get('mo_id') or '').strip()
    stat_id = (request.GET.get('stat') or '').strip()
    if not mo_id.isdigit():
        return JsonResponse({'error': 'Thiếu lệnh sản xuất.'}, status=400)
    mo = SxProductionOrder.objects.filter(pk=int(mo_id), is_demo=False).first()
    if not mo:
        return JsonResponse({'error': 'Không tìm thấy lệnh sản xuất.'}, status=404)
    stat = None
    if stat_id.isdigit():
        stat = SxProductionStat.objects.filter(pk=int(stat_id), production_order=mo).first()
    return JsonResponse(fg_receipt_prefill(mo=mo, stat=stat))


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
    """Danh sách hồ sơ thiết kế (BOM) theo mã SX — kèm gợi ý tổ / công đoạn."""
    from django.urls import reverse

    product_code = (request.GET.get('product_code') or '').strip()
    from san_xuat.forms_dispatch import _process_defaults_from_bom
    from san_xuat.models import ProductTechDoc
    from san_xuat.services.capacity_from_hrm import (
        default_manager_user_id_for_work_center,
        mo_form_work_center_id,
    )

    results = []
    doc = None
    if product_code:
        doc = ProductTechDoc.objects.filter(product_code__iexact=product_code).first()
        if doc:
            for bom in doc.bom_versions.prefetch_related('process_steps__work_center').order_by('created_at', 'id'):
                note = (bom.notes or '').strip()
                n_steps = bom.process_steps.count()
                team, process = _process_defaults_from_bom(bom)
                label = bom.version_label or f'#{bom.pk}'
                text = label
                if n_steps:
                    text = f'{label} · {n_steps} công đoạn'
                if note:
                    text = f'{text} — {note[:40]}'
                steps = []
                for s in bom.process_steps.select_related('work_center').order_by('sequence', 'id')[:80]:
                    wc_id = mo_form_work_center_id(
                        work_center=s.work_center,
                        work_center_id=s.work_center_id,
                        work_center_code=(s.work_center.code if s.work_center_id else '') or '',
                        name_hint=s.process_name or '',
                    ) or s.work_center_id
                    steps.append({
                        'id': s.pk,
                        'sequence': s.sequence,
                        'process_name': s.process_name,
                        'work_center_id': wc_id,
                        'manager_id': default_manager_user_id_for_work_center(wc_id) or '',
                        'team_label': (
                            (s.work_center.team_label or s.work_center.name)
                            if s.work_center_id else ''
                        ),
                    })
                results.append({
                    'id': bom.pk,
                    'tech_doc_id': doc.pk,
                    'label': label,
                    'text': text,
                    'notes': note,
                    'n_steps': n_steps,
                    'team_label': team,
                    'process_name': process,
                    'process_steps': steps,
                })
    return JsonResponse({
        'results': results,
        'product_code': product_code,
        'tech_doc_id': doc.pk if doc else None,
        'doc_url': reverse('san_xuat:doc_detail', kwargs={'pk': doc.pk}) if doc else '',
        'create_url': reverse('san_xuat:doc_create') + (
            f'?code={product_code}' if product_code else ''
        ),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def process_catalog_search(request):
    """Gõ tìm công đoạn chuẩn trong thư viện IE.

    Trả thêm default_work_center_id để JS tự điền bộ phận khi chọn công đoạn.
    """
    q = (request.GET.get('q') or '').strip()
    from django.db.models import Q as _Q

    from san_xuat.ie_models import SxOperation
    from san_xuat.services.process_catalog import _STANDARD_STATUSES, _hr_work_center_id

    # Lấy từ IE: name_vi + default_work_center qua group
    qs = (
        SxOperation.objects.filter(status__in=_STANDARD_STATUSES)
        .exclude(name_vi='')
        .select_related('group__default_work_center')
        .order_by('name_vi')
    )
    if q:
        qs = qs.filter(name_vi__icontains=q)

    seen: dict[str, dict] = {}
    for op in qs[:300]:
        name = (op.name_vi or '').strip()
        if not name or name.casefold() in seen:
            continue
        grp = op.group
        wc_id = None
        wc_name = ''
        if grp:
            wc_id = _hr_work_center_id(
                work_center=grp.default_work_center,
                work_center_code=grp.default_work_center_code or '',
                name_hint=f'{grp.process_stage_label} {grp.name} {name}',
            )
            if wc_id and grp.default_work_center_id == wc_id and grp.default_work_center:
                wc_name = grp.default_work_center.name or ''
        seen[name.casefold()] = {
            'id': name,
            'name': name,
            'text': name,
            'default_work_center_id': wc_id,
            'default_work_center_name': wc_name,
        }
        if len(seen) >= 60:
            break

    rows = list(seen.values())
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
