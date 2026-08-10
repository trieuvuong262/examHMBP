"""Giao diện web cho Master Data mã công đoạn sản xuất (IE).

- Trang tổng quan + import/export file Excel.
- Thư viện công đoạn chuẩn.
- Routing mã hàng (danh sách + chi tiết).
- Dữ liệu bấm giờ (time study) + duyệt cập nhật SMV.
"""

from __future__ import annotations

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from assessment.decorators import module_perm_required
from hrm.module_permissions import (
    MODULE_SAN_XUAT,
    user_can_create_module,
    user_can_export_module,
    user_can_update_module,
)
from PortalJustPlay.pagination import paginate_queryset

from san_xuat.ie_models import (
    SxIeAuditLog,
    SxMachine,
    SxOperation,
    SxOperationGroup,
    SxProcessStage,
    SxRouting,
    SxRoutingLine,
    SxSkillLevel,
    SxSmvSource,
    SxStitchClass,
    SxTimeStudy,
)
from san_xuat.ie_permissions import (
    IE_APPROVER_GROUP,
    ie_approver_group_has_members,
    user_can_approve_ie,
)
from san_xuat.services.ie_ops import (
    IeOpsError,
    approve_operation,
    approve_routing,
    approve_time_study,
    build_ie_dashboard,
    clone_routing_revision,
    delete_routing_line,
    is_routing_locked,
    link_time_studies_to_operations,
    reject_routing,
    reject_time_study,
    save_routing_line_explanations,
    update_operation,
    upsert_routing_line,
)
from san_xuat.services.operation_master import (
    OperationMasterImportError,
    export_operation_master_response,
    import_operation_master,
)


def _perm_ctx(request):
    return {
        'can_create': user_can_create_module(request.user, MODULE_SAN_XUAT),
        'can_update': user_can_update_module(request.user, MODULE_SAN_XUAT),
        'can_export': user_can_export_module(request.user, MODULE_SAN_XUAT),
        'can_approve': user_can_approve_ie(request.user),
        'approver_group_ready': ie_approver_group_has_members(),
        'approver_group_name': IE_APPROVER_GROUP,
    }


def _dec(raw, default='0'):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(raw if raw not in (None, '') else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_hub(request):
    perms = _perm_ctx(request)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'import':
            if not (perms['can_create'] or perms['can_update']):
                messages.error(request, 'Bạn không có quyền import dữ liệu.')
                return redirect('san_xuat:ie_hub')
            upload = request.FILES.get('excel_file')
            if not upload:
                messages.error(request, 'Chưa chọn file Excel.')
                return redirect('san_xuat:ie_hub')
            if not upload.name.lower().endswith(('.xlsx', '.xlsm')):
                messages.error(request, 'File phải là định dạng .xlsx.')
                return redirect('san_xuat:ie_hub')
            dry_run = request.POST.get('dry_run') == '1'
            try:
                result = import_operation_master(upload, dry_run=dry_run, user=request.user)
            except OperationMasterImportError as exc:
                messages.error(request, f'Lỗi import: {exc}')
                return redirect('san_xuat:ie_hub')

            prefix = 'THỬ (không lưu) — ' if dry_run else ''
            summary = ', '.join(f'{k}: {v}' for k, v in sorted(result.created.items())) or 'không có bản ghi mới'
            messages.success(
                request,
                f'{prefix}Import xong. Tạo mới {result.total_created}, cập nhật {result.total_updated}. Chi tiết: {summary}.',
            )
            for w in result.warnings[:15]:
                messages.warning(request, w)
            if len(result.warnings) > 15:
                messages.warning(request, f'… và {len(result.warnings) - 15} cảnh báo khác.')
            return redirect('san_xuat:ie_hub')

        if action == 'create_routing':
            if not (perms['can_create'] or perms['can_update']):
                messages.error(request, 'Bạn không có quyền tạo routing.')
                return redirect('san_xuat:ie_hub')
            from san_xuat.services.ie_ops import create_blank_routing

            style_code = (request.POST.get('style_code') or '').strip()
            style_name = (request.POST.get('style_name') or '').strip()
            routing_rev = (request.POST.get('routing_rev') or 'R01').strip() or 'R01'
            if not style_code:
                messages.error(request, 'Nhập mã hàng.')
                return redirect('san_xuat:ie_hub')
            seed = f'{style_code}-{routing_rev}'
            try:
                routing = create_blank_routing(
                    style_code=seed,
                    routing_id=seed,
                    style_name=style_name,
                    user=request.user,
                )
            except IeOpsError as exc:
                messages.error(request, str(exc))
                return redirect('san_xuat:ie_hub')
            messages.success(request, f'Đã tạo routing tay {routing.routing_id}.')
            return redirect('san_xuat:ie_routing_detail', pk=routing.pk)

        if action == 'create_operation':
            if not (perms['can_create'] or perms['can_update']):
                messages.error(request, 'Bạn không có quyền tạo công đoạn.')
                return redirect('san_xuat:ie_hub')
            from decimal import Decimal, InvalidOperation

            from san_xuat.services.ie_ops import create_blank_operation

            op_code = (request.POST.get('op_code') or '').strip()
            name_vi = (request.POST.get('name_vi') or '').strip()
            op_rev = (request.POST.get('op_rev') or 'R01').strip() or 'R01'
            group_id = (request.POST.get('group_id') or '').strip()
            machine_code = (request.POST.get('machine_code') or '').strip()
            smv_raw = (request.POST.get('base_smv_min') or '').strip()
            try:
                smv = Decimal(smv_raw) if smv_raw else Decimal('0')
            except (InvalidOperation, ValueError):
                messages.error(request, 'SMV không hợp lệ.')
                return redirect('san_xuat:ie_hub')
            group = None
            if group_id.isdigit():
                group = SxOperationGroup.objects.filter(pk=int(group_id)).first()
            try:
                op = create_blank_operation(
                    op_code=op_code,
                    name_vi=name_vi,
                    group=group,
                    op_rev=op_rev,
                    base_smv_min=smv,
                    machine_code=machine_code,
                )
            except IeOpsError as exc:
                messages.error(request, str(exc))
                return redirect('san_xuat:ie_hub')
            messages.success(request, f'Đã tạo công đoạn chuẩn {op.op_code}/{op.op_rev}.')
            return redirect(f"{reverse('san_xuat:ie_operation_list')}?q={op.op_code}")

        if action == 'create_group':
            if not (perms['can_create'] or perms['can_update']):
                messages.error(request, 'Bạn không có quyền tạo nhóm.')
                return redirect('san_xuat:ie_hub')
            from san_xuat.services.ie_ops import create_operation_group

            try:
                group = create_operation_group(
                    code=(request.POST.get('group_code') or '').strip(),
                    name=(request.POST.get('group_name') or '').strip(),
                    process_stage_label=(request.POST.get('process_stage_label') or '').strip(),
                    product_part=(request.POST.get('product_part') or '').strip(),
                )
            except IeOpsError as exc:
                messages.error(request, str(exc))
                return redirect('san_xuat:ie_hub')
            messages.success(request, f'Đã tạo nhóm {group.code}.')
            return redirect(f"{reverse('san_xuat:ie_group_list')}?q={group.code}")

        if action == 'create_time_study':
            if not (perms['can_create'] or perms['can_update']):
                messages.error(request, 'Bạn không có quyền tạo bấm giờ.')
                return redirect('san_xuat:ie_hub')
            from decimal import Decimal, InvalidOperation

            from san_xuat.services.ie_ops import create_time_study

            def _dec(key, default='0'):
                raw = (request.POST.get(key) or '').strip()
                if not raw:
                    return Decimal(default)
                try:
                    return Decimal(raw)
                except (InvalidOperation, ValueError) as exc:
                    raise IeOpsError(f'Giá trị {key} không hợp lệ.') from exc

            try:
                study = create_time_study(
                    op_code=(request.POST.get('ts_op_code') or '').strip(),
                    op_name_vi=(request.POST.get('ts_op_name') or '').strip(),
                    style_code=(request.POST.get('ts_style_code') or '').strip(),
                    observed_cycle_sec=_dec('observed_cycle_sec'),
                    abnormal_sec=_dec('abnormal_sec'),
                    performance_rating=_dec('performance_rating', '1'),
                    allowance_pct=_dec('allowance_pct'),
                    current_routing_smv=_dec('current_routing_smv'),
                )
            except IeOpsError as exc:
                messages.error(request, str(exc))
                return redirect('san_xuat:ie_hub')
            messages.success(
                request,
                f'Đã tạo bấm giờ {study.study_id} — SMV tính = {study.calculated_smv} phút.',
            )
            return redirect('san_xuat:ie_time_study_list')

        if action == 'link_time_studies':
            if not perms['can_update']:
                messages.error(request, 'Bạn không có quyền gắn liên kết.')
                return redirect('san_xuat:ie_hub')
            stats = link_time_studies_to_operations(only_unlinked=True)
            from san_xuat.services.ie_audit import log_ie_event

            log_ie_event(
                action=SxIeAuditLog.ACTION_LINK,
                summary=f"Gắn FK time study → operation: {stats['linked']} quan sát",
                object_type='SxTimeStudy',
                object_repr='bulk_link',
                changes=stats,
                user=request.user,
            )
            messages.success(
                request,
                f"Đã gắn {stats['linked']} quan sát; bỏ qua {stats['skipped']}.",
            )
            return redirect('san_xuat:ie_hub')

    stats = {
        'machines': SxMachine.objects.count(),
        'stitch_classes': SxStitchClass.objects.count(),
        'skill_levels': SxSkillLevel.objects.count(),
        'smv_sources': SxSmvSource.objects.count(),
        'process_stages': SxProcessStage.objects.count(),
        'groups': SxOperationGroup.objects.count(),
        'operations': SxOperation.objects.count(),
        'operations_approved': SxOperation.objects.filter(status=SxOperation.STATUS_APPROVED).count(),
        'routings': SxRouting.objects.count(),
        'routing_lines': SxRoutingLine.objects.count(),
        'time_studies': SxTimeStudy.objects.count(),
    }
    routings = (
        SxRouting.objects.annotate(
            n_lines=Count('lines'),
            sum_smv=Sum('lines__total_operation_smv'),
        ).order_by('style_code', 'routing_rev')
    )
    return render(request, 'san_xuat/ie_hub.html', {
        **perms,
        'stats': stats,
        'routings': routings,
        'operation_groups': SxOperationGroup.objects.filter(is_active=True).order_by('sort_order', 'code'),
    })


@module_perm_required(MODULE_SAN_XUAT, 'export')
@require_GET
def ie_export(request):
    return export_operation_master_response(user=request.user)


@module_perm_required(MODULE_SAN_XUAT, 'view')
def group_list(request):
    qs = (
        SxOperationGroup.objects.select_related('default_work_center')
        .annotate(n_ops=Count('operations'))
        .all()
    )
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(code__icontains=term)
            | Q(name__icontains=term)
            | Q(process_stage_label__icontains=term)
            | Q(product_part__icontains=term)
            | Q(default_work_center__name__icontains=term)
            | Q(default_work_center_code__icontains=term)
        )
    qs = qs.order_by('sort_order', 'code')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_group_list.html', {
        **_perm_ctx(request),
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'total': qs.count(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def machine_list(request):
    qs = SxMachine.objects.annotate(n_ops=Count('operations')).all()
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(Q(code__icontains=term) | Q(name__icontains=term) | Q(notes__icontains=term))
    qs = qs.order_by('sort_order', 'code')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_machine_list.html', {
        **_perm_ctx(request),
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'total': qs.count(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def routing_line_list(request):
    qs = SxRoutingLine.objects.select_related('routing', 'operation', 'machine', 'work_center').all()
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(op_code__icontains=term)
            | Q(op_name_vi__icontains=term)
            | Q(routing__style_code__icontains=term)
            | Q(routing__routing_id__icontains=term)
            | Q(machine_code__icontains=term)
            | Q(work_center_code__icontains=term)
            | Q(work_center__name__icontains=term)
        )
    qs = qs.order_by('routing__style_code', 'routing__routing_rev', 'seq_no')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_routing_line_list.html', {
        **_perm_ctx(request),
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'total': qs.count(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def operation_list(request):
    perms = _perm_ctx(request)
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        pk = request.POST.get('pk')
        op = SxOperation.objects.filter(pk=int(pk)).first() if pk and str(pk).isdigit() else None
        if action == 'approve_operation' and op:
            if not perms['can_approve']:
                messages.error(request, 'Bạn không có quyền duyệt công đoạn (cần nhóm Approver IE).')
            else:
                try:
                    approve_operation(operation=op, user=request.user)
                    messages.success(request, f'Đã duyệt {op.op_code}/{op.op_rev}.')
                except IeOpsError as exc:
                    messages.error(request, str(exc))
        else:
            messages.error(request, 'Không duyệt được công đoạn.')
        return redirect(request.get_full_path() if request.GET else 'san_xuat:ie_operation_list')

    qs = SxOperation.objects.select_related('group', 'machine', 'skill_level').all()

    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(op_code__icontains=term)
            | Q(name_vi__icontains=term)
            | Q(name_en__icontains=term)
            | Q(machine_code__icontains=term)
        )
    group_code = (request.GET.get('group') or '').strip()
    if group_code:
        qs = qs.filter(group__code=group_code)
    status = (request.GET.get('status') or '').strip()
    if status:
        qs = qs.filter(status=status)
    else:
        # Mặc định ẩn OP đã ngưng — thư viện chỉ hiện bộ chuẩn đang dùng
        qs = qs.exclude(status=SxOperation.STATUS_RETIRED)

    qs = qs.order_by('op_code', 'op_rev')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_operation_list.html', {
        **perms,
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'group_code': group_code,
        'status': status,
        'groups': SxOperationGroup.objects.order_by('sort_order', 'code'),
        'status_choices': SxOperation.STATUS_CHOICES,
        'total': qs.count(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def operation_detail(request, pk: int):
    op = get_object_or_404(
        SxOperation.objects.select_related('group', 'machine', 'skill_level', 'stitch_class', 'smv_source'),
        pk=pk,
    )
    perms = _perm_ctx(request)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'approve_operation':
                if not perms['can_approve']:
                    raise IeOpsError('Bạn không có quyền duyệt công đoạn.')
                approve_operation(operation=op, user=request.user)
                messages.success(request, f'Đã duyệt {op.op_code}/{op.op_rev}.')
            elif action == 'save_operation':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa công đoạn.')
                group = None
                gid = (request.POST.get('group_id') or '').strip()
                if gid.isdigit():
                    group = SxOperationGroup.objects.filter(pk=int(gid)).first()
                smv_raw = (request.POST.get('base_smv_min') or '').strip()
                smv = _dec(smv_raw) if smv_raw != '' else None
                status = (request.POST.get('status') or '').strip() or None
                update_operation(
                    operation=op,
                    user=request.user,
                    name_vi=request.POST.get('name_vi'),
                    name_en=request.POST.get('name_en'),
                    group=group,
                    process_stage_label=request.POST.get('process_stage_label'),
                    product_part=request.POST.get('product_part'),
                    method_variant=request.POST.get('method_variant'),
                    machine_code=request.POST.get('machine_code'),
                    skill_level_label=request.POST.get('skill_level_label'),
                    stitch_class_code=request.POST.get('stitch_class_code'),
                    smv_source_code=request.POST.get('smv_source_code'),
                    base_smv_min=smv,
                    smv_basis=request.POST.get('smv_basis'),
                    qc_criteria=request.POST.get('qc_criteria'),
                    status=status if status != SxOperation.STATUS_APPROVED else None,
                    ie_owner=request.POST.get('ie_owner'),
                    revision_reason=request.POST.get('revision_reason'),
                    notes=request.POST.get('notes'),
                    work_instruction_url=request.POST.get('work_instruction_url'),
                    video_url=request.POST.get('video_url'),
                )
                messages.success(request, f'Đã lưu {op.op_code}/{op.op_rev}.')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return redirect('san_xuat:ie_operation_detail', pk=op.pk)

    product_parts = list(
        SxOperation.objects.exclude(product_part='')
        .order_by('product_part')
        .values_list('product_part', flat=True)
        .distinct()
    )
    if op.product_part and op.product_part not in product_parts:
        product_parts = [op.product_part] + product_parts
    smv_basis_choices = list(
        SxOperation.objects.exclude(smv_basis='')
        .order_by('smv_basis')
        .values_list('smv_basis', flat=True)
        .distinct()
    )
    if op.smv_basis and op.smv_basis not in smv_basis_choices:
        smv_basis_choices = [op.smv_basis] + smv_basis_choices
    ie_owners = list(
        SxOperation.objects.exclude(ie_owner='')
        .order_by('ie_owner')
        .values_list('ie_owner', flat=True)
        .distinct()
    )
    if op.ie_owner and op.ie_owner not in ie_owners:
        ie_owners = [op.ie_owner] + ie_owners

    return render(request, 'san_xuat/ie_operation_detail.html', {
        **perms,
        'op': op,
        'groups': SxOperationGroup.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'machines': SxMachine.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'skill_levels': SxSkillLevel.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'process_stages': SxProcessStage.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'stitch_classes': SxStitchClass.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'smv_sources': SxSmvSource.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'product_parts': product_parts,
        'smv_basis_choices': smv_basis_choices,
        'ie_owners': ie_owners,
        'status_choices': [
            c for c in SxOperation.STATUS_CHOICES if c[0] != SxOperation.STATUS_APPROVED
        ],
        'audit_logs': SxIeAuditLog.objects.filter(
            object_type='SxOperation', object_id=str(op.pk)
        )[:20],
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def routing_list(request):
    qs = SxRouting.objects.annotate(
        n_lines=Count('lines'),
        sum_smv=Sum('lines__total_operation_smv'),
    )
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(routing_id__icontains=term)
            | Q(style_code__icontains=term)
            | Q(style_name__icontains=term)
        )
    qs = qs.order_by('style_code', 'routing_rev')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_routing_list.html', {
        **_perm_ctx(request),
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'total': qs.count(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def routing_detail(request, pk: int):
    routing = get_object_or_404(SxRouting, pk=pk)
    perms = _perm_ctx(request)
    locked = is_routing_locked(routing)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'approve_routing':
                if not perms['can_approve']:
                    raise IeOpsError('Bạn không có quyền duyệt routing (cần nhóm Approver IE).')
                approve_routing(routing=routing, user=request.user)
                messages.success(request, f'Đã duyệt routing {routing.routing_id}.')
            elif action == 'reject_routing':
                if not perms['can_approve']:
                    raise IeOpsError('Bạn không có quyền từ chối routing (cần nhóm Approver IE).')
                reject_routing(routing=routing, user=request.user)
                messages.success(request, f'Đã từ chối routing {routing.routing_id}.')
            elif action == 'clone_revision':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền tạo phiên bản routing.')
                clone = clone_routing_revision(routing=routing, user=request.user)
                messages.success(request, f'Đã tạo phiên bản mới {clone.routing_id}.')
                return redirect('san_xuat:ie_routing_detail', pk=clone.pk)
            elif action == 'save_explanations':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa giải trình.')
                explanations = {}
                for key, val in request.POST.items():
                    if key.startswith('expl_') and key[5:].isdigit():
                        explanations[int(key[5:])] = val
                n = save_routing_line_explanations(routing=routing, explanations=explanations)
                messages.success(request, f'Đã lưu {n} giải trình lệch SMV.')
            elif action in ('add_line', 'edit_line'):
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa dòng routing.')
                line_pk = request.POST.get('line_pk')
                line_pk = int(line_pk) if line_pk and str(line_pk).isdigit() else None
                seq_raw = (request.POST.get('seq_no') or '').strip()
                upsert_routing_line(
                    routing=routing,
                    line_pk=line_pk if action == 'edit_line' else None,
                    seq_no=int(seq_raw) if seq_raw.isdigit() else None,
                    op_code=(request.POST.get('op_code') or '').strip(),
                    op_rev=(request.POST.get('op_rev') or 'R01').strip(),
                    op_name_vi=(request.POST.get('op_name_vi') or '').strip(),
                    group_code=(request.POST.get('group_code') or '').strip(),
                    qty_per_garment=_dec(request.POST.get('qty_per_garment'), '1'),
                    applied_unit_smv=_dec(request.POST.get('applied_unit_smv')),
                    library_unit_smv=_dec(request.POST.get('library_unit_smv'))
                    if (request.POST.get('library_unit_smv') or '').strip() != ''
                    else None,
                    machine_code=(request.POST.get('machine_code') or '').strip(),
                    work_center_code=(request.POST.get('work_center_code') or '').strip(),
                    variance_explanation=(request.POST.get('variance_explanation') or '').strip(),
                    notes=(request.POST.get('notes') or '').strip(),
                )
                messages.success(request, 'Đã lưu dòng routing.')
            elif action == 'delete_line':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền xóa dòng routing.')
                line_pk = request.POST.get('line_pk')
                if not line_pk or not str(line_pk).isdigit():
                    raise IeOpsError('Thiếu dòng cần xóa.')
                delete_routing_line(routing=routing, line_pk=int(line_pk))
                messages.success(request, 'Đã xóa dòng routing.')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return redirect('san_xuat:ie_routing_detail', pk=routing.pk)

    lines = routing.lines.select_related('operation', 'machine', 'work_center').order_by('seq_no')
    high_var = [l for l in lines if abs(l.smv_variance_pct or 0) > 15]
    edit_line = None
    edit_pk = (request.GET.get('edit') or '').strip()
    if edit_pk.isdigit() and perms['can_update'] and not locked:
        edit_line = routing.lines.filter(pk=int(edit_pk)).first()
    from san_xuat.services.capacity_from_hrm import hr_work_centers_qs
    work_centers = list(hr_work_centers_qs())
    return render(request, 'san_xuat/ie_routing_detail.html', {
        **perms,
        'routing': routing,
        'lines': lines,
        'total_smv': routing.total_smv,
        'locked': locked,
        'high_var_count': len(high_var),
        'edit_line': edit_line,
        'machines': SxMachine.objects.filter(is_active=True).order_by('sort_order', 'code')[:200],
        'work_centers': work_centers,
        'default_work_center_code': '',
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def time_study_list(request):
    perms = _perm_ctx(request)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        pk = request.POST.get('pk')
        study = None
        if pk and str(pk).isdigit():
            study = SxTimeStudy.objects.filter(pk=int(pk)).first()
        if not study:
            messages.error(request, 'Không tìm thấy quan sát.')
            return redirect('san_xuat:ie_time_study_list')

        try:
            if action == 'approve':
                if not perms['can_approve']:
                    raise IeOpsError('Bạn không có quyền duyệt bấm giờ (cần nhóm Approver IE).')
                result = approve_time_study(
                    study=study,
                    update_routing=request.POST.get('update_routing') != '0',
                    update_library=request.POST.get('update_library') == '1',
                    variance_explanation=(request.POST.get('variance_explanation') or '').strip(),
                    user=request.user,
                )
                msg = (
                    f'Đã duyệt {result.study_id}. SMV mới {result.new_smv} phút '
                    f'(n={result.sample_count}), cập nhật {result.routing_lines_updated} dòng routing'
                )
                if result.library_updated:
                    msg += ', đã cập nhật thư viện'
                messages.success(request, msg + '.')
                for w in result.warnings:
                    messages.warning(request, w)
            elif action == 'reject':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền từ chối quan sát.')
                reject_time_study(study=study, status=SxTimeStudy.APPROVAL_REJECTED)
                messages.success(request, f'Đã từ chối {study.study_id}.')
            elif action == 'remeasure':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền đánh dấu đo lại.')
                reject_time_study(study=study, status=SxTimeStudy.APPROVAL_REMEASURE)
                messages.success(request, f'Đánh dấu cần đo lại: {study.study_id}.')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return redirect(request.get_full_path() if request.GET else 'san_xuat:ie_time_study_list')

    qs = SxTimeStudy.objects.select_related('operation').all()
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(study_id__icontains=term)
            | Q(op_code__icontains=term)
            | Q(op_name_vi__icontains=term)
            | Q(operator_id__icontains=term)
            | Q(style_code__icontains=term)
        )
    status = (request.GET.get('status') or '').strip()
    if status:
        qs = qs.filter(approval_status=status)
    qs = qs.order_by('op_code', 'obs_no', 'study_id')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_time_study_list.html', {
        **perms,
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'status': status,
        'status_choices': SxTimeStudy.APPROVAL_CHOICES,
        'total': qs.count(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_dashboard(request):
    import json

    data = build_ie_dashboard()
    return render(request, 'san_xuat/ie_dashboard.html', {
        **_perm_ctx(request),
        **data,
        'chart_style_labels_json': json.dumps(data['chart_style_labels'], ensure_ascii=False),
        'chart_total_smv_json': json.dumps(data['chart_total_smv']),
        'chart_sew_smv_json': json.dumps(data['chart_sew_smv']),
        'chart_other_smv_json': json.dumps(data['chart_other_smv']),
        'chart_op_status_json': json.dumps(data['chart_op_status']),
        'chart_routing_status_json': json.dumps(data['chart_routing_status']),
        'chart_ts_status_json': json.dumps(data['chart_ts_status']),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_audit_list(request):
    qs = SxIeAuditLog.objects.select_related('user').all()
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(summary__icontains=term)
            | Q(object_repr__icontains=term)
            | Q(username__icontains=term)
            | Q(object_type__icontains=term)
        )
    action = (request.GET.get('action') or '').strip()
    if action:
        qs = qs.filter(action=action)
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_audit_list.html', {
        **_perm_ctx(request),
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'action': action,
        'action_choices': SxIeAuditLog.ACTION_CHOICES,
        'total': qs.count(),
    })
