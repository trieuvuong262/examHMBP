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

    if request.method == 'POST' and request.POST.get('action') == 'import':
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
    stage_rows = (
        SxOperationGroup.objects.values('process_stage_label')
        .annotate(n=Count('id'))
        .order_by('process_stage_label')
    )
    return render(request, 'san_xuat/ie_hub.html', {
        **perms,
        'stats': stats,
        'routings': routings,
        'stage_rows': stage_rows,
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
