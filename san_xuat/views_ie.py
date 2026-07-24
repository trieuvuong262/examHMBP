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
from san_xuat.services.ie_ops import IeOpsError, approve_time_study, reject_time_study
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
    }


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
                result = import_operation_master(upload, dry_run=dry_run)
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
            return redirect('san_xuat:ie_hub')

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
    return export_operation_master_response()


@module_perm_required(MODULE_SAN_XUAT, 'view')
def operation_list(request):
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

    qs = qs.order_by('op_code', 'op_rev')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_operation_list.html', {
        **_perm_ctx(request),
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
    lines = routing.lines.select_related('operation', 'machine', 'work_center').order_by('seq_no')
    return render(request, 'san_xuat/ie_routing_detail.html', {
        **_perm_ctx(request),
        'routing': routing,
        'lines': lines,
        'total_smv': routing.total_smv,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def time_study_list(request):
    perms = _perm_ctx(request)

    if request.method == 'POST' and perms['can_update']:
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
                result = approve_time_study(
                    study=study,
                    update_routing=request.POST.get('update_routing') != '0',
                    update_library=request.POST.get('update_library') == '1',
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
                reject_time_study(study=study, status=SxTimeStudy.APPROVAL_REJECTED)
                messages.success(request, f'Đã từ chối {study.study_id}.')
            elif action == 'remeasure':
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
