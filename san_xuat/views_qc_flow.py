"""Màn QC inline / endline / preaudit."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from assessment.decorators import module_perm_required
from hrm.menu_permissions import (
    handle_menu_access_denied,
    user_can_access_menu,
    user_can_create_menu,
    user_can_delete_menu,
    user_can_update_menu,
)
from hrm.module_permissions import MODULE_SAN_XUAT
from san_xuat.forms_qc_flow import QcFlowCheckForm
from san_xuat.hub_models import (
    SxProductionOrder,
    SxQcDefect,
    SxQcDefectGroup,
    SxQcFlowCheck,
    SxQcFlowDefectLine,
)
from san_xuat.list_filters import SX_FILTER_QC_BOARD, prepare_hub_list
from san_xuat.services.qc_flow import (
    FLOWS,
    aql_fixed_bands,
    blank_defect_slots,
    flow_board,
    flow_meta,
    inline_stages_by_team,
    parse_defect_rows,
    parse_size_rows,
    passed_endline,
    save_flow_check,
    size_form_rows,
)
from san_xuat.services.qc import QcError
from san_xuat.views import _perm_ctx


def _can_open(user) -> bool:
    return any(
        user_can_access_menu(user, MODULE_SAN_XUAT, key)
        for key in ('qc', 'qc_request', 'qc_sheet', 'qc_defect', 'qc_defect_group')
    )


def _can_write(user) -> bool:
    return any((
        user_can_update_menu(user, MODULE_SAN_XUAT, 'qc'),
        user_can_create_menu(user, MODULE_SAN_XUAT, 'qc_sheet'),
        user_can_update_menu(user, MODULE_SAN_XUAT, 'qc_sheet'),
        user_can_create_menu(user, MODULE_SAN_XUAT, 'qc_request'),
        user_can_update_menu(user, MODULE_SAN_XUAT, 'qc_request'),
        user_can_create_menu(user, MODULE_SAN_XUAT, 'qc_defect'),
        user_can_update_menu(user, MODULE_SAN_XUAT, 'qc_defect'),
        user_can_update_menu(user, MODULE_SAN_XUAT, 'qc_defect_group'),
    ))


def _guard(request):
    if not _can_open(request.user):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'qc')
    return None


def _flow_or_redirect(request, flow: str):
    if flow not in FLOWS:
        messages.error(request, 'Luồng QC không hợp lệ.')
        return None
    return flow


def _mo_from_request(request, *, source: str = 'GET') -> SxProductionOrder | None:
    bag = request.POST if source == 'POST' else request.GET
    raw = (bag.get('mo') or bag.get('production_order') or '').strip()
    if raw.isdigit():
        return SxProductionOrder.objects.filter(pk=int(raw), is_demo=False).first()
    return None


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_home(request):
    denied = _guard(request)
    if denied:
        return denied
    base = (
        SxProductionOrder.objects.filter(is_demo=False)
        .exclude(status__in=[
            SxProductionOrder.STATUS_DRAFT,
            SxProductionOrder.STATUS_CANCELLED,
        ])
        .select_related('sales_order', 'created_by')
        .order_by('-order_date', '-pk')
    )
    orders, fctx = prepare_hub_list(
        request,
        base,
        SX_FILTER_QC_BOARD,
        list_key='qc_board',
        status_choices=[
            choice for choice in SxProductionOrder.STATUS_CHOICES
            if choice[0] not in (
                SxProductionOrder.STATUS_DRAFT,
                SxProductionOrder.STATUS_CANCELLED,
            )
        ],
    )
    return render(request, 'san_xuat/hub_qc.html', {
        **_perm_ctx(request),
        'board': flow_board(list(orders)),
        'can_write_qc': _can_write(request.user),
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_flow_list(request, flow: str):
    denied = _guard(request)
    if denied:
        return denied
    if not _flow_or_redirect(request, flow):
        return redirect('san_xuat:qc_stub')
    meta = flow_meta(flow)
    qs = (
        SxQcFlowCheck.objects.filter(is_demo=False, flow=flow)
        .select_related('production_order', 'production_order__sales_order')
        .order_by('-checked_on', '-pk')
    )
    mo = _mo_from_request(request)
    if mo is not None:
        qs = qs.filter(production_order=mo)
    term = (request.GET.get('q') or '').strip()
    if term:
        from django.db.models import Q

        qs = qs.filter(
            Q(code__icontains=term)
            | Q(product_code__icontains=term)
            | Q(product_name__icontains=term)
            | Q(production_order__code__icontains=term)
            | Q(stage_name__icontains=term)
        )
    return render(request, 'san_xuat/qc_flow_list.html', {
        **_perm_ctx(request),
        'flow': flow,
        'meta': meta,
        'checks': qs[:200],
        'search_query': term,
        'mo': mo,
        'can_write_qc': _can_write(request.user),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_http_methods(['GET', 'POST'])
def qc_flow_create(request, flow: str):
    denied = _guard(request)
    if denied:
        return denied
    if not _flow_or_redirect(request, flow):
        return redirect('san_xuat:qc_stub')
    if request.method == 'POST' and not _can_write(request.user):
        messages.error(request, 'Bạn không có quyền tạo phiếu QC.')
        return redirect('san_xuat:qc_flow_list', flow=flow)
    return _edit(request, flow=flow, check=None)


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_http_methods(['GET', 'POST'])
def qc_flow_detail(request, flow: str, pk: int):
    denied = _guard(request)
    if denied:
        return denied
    if not _flow_or_redirect(request, flow):
        return redirect('san_xuat:qc_stub')
    check = get_object_or_404(
        SxQcFlowCheck.objects.select_related('production_order'),
        pk=pk,
        flow=flow,
        is_demo=False,
    )
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        if check.status != SxQcFlowCheck.STATUS_DRAFT:
            messages.error(request, 'Chỉ xóa được phiếu nháp.')
            return redirect('san_xuat:qc_flow_detail', flow=flow, pk=check.pk)
        if not (
            user_can_delete_menu(request.user, MODULE_SAN_XUAT, 'qc_sheet')
            or user_can_delete_menu(request.user, MODULE_SAN_XUAT, 'qc_request')
            or _can_write(request.user)
        ):
            messages.error(request, 'Bạn không có quyền xóa phiếu QC.')
            return redirect('san_xuat:qc_flow_detail', flow=flow, pk=check.pk)
        code = check.code
        check.delete()
        messages.success(request, f'Đã xóa {code}.')
        return redirect('san_xuat:qc_flow_list', flow=flow)
    return _edit(request, flow=flow, check=check)


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_flow_open(request, pk: int):
    denied = _guard(request)
    if denied:
        return denied
    check = get_object_or_404(SxQcFlowCheck, pk=pk, is_demo=False)
    return redirect('san_xuat:qc_flow_detail', flow=check.flow, pk=check.pk)


def _initial_from_mo(mo: SxProductionOrder | None, flow: str) -> dict:
    if mo is None:
        return {}
    initial = {'production_order': mo.pk}
    if flow == SxQcFlowCheck.FLOW_ENDLINE:
        initial['team_slug'] = 'may'
    if flow == SxQcFlowCheck.FLOW_PREAUDIT:
        initial['qty_lot'] = mo.qty
    return initial


def _initial_from_check(check: SxQcFlowCheck) -> dict:
    return {
        'production_order': check.production_order_id,
        'team_slug': check.team_slug,
        'stage_name': check.stage_name,
        'checked_on': check.checked_on,
        'qty_lot': check.qty_lot,
        'notes': check.notes,
    }


def _pad_defects(rows: list[dict]) -> list[dict]:
    out = list(rows)
    while len(out) < 4:
        out.append({
            'defect_id': '',
            'defect_name': '',
            'size_label': '',
            'qty': '',
            'severity': SxQcFlowDefectLine.SEVERITY_MAJOR,
        })
    return out


def _mo_for_sheet(form, fallback):
    if form.is_bound:
        raw = (form.data.get('production_order') or '').strip()
        if raw.isdigit():
            found = SxProductionOrder.objects.filter(pk=int(raw), is_demo=False).first()
            if found is not None:
                return found
    return fallback


def _aql_preview(lot):
    from decimal import Decimal

    from san_xuat.services.aql import AqlError, aql_sample_plan

    try:
        return aql_sample_plan(lot_size=lot or 0, aql=Decimal('2.5'), inspection_level='II')
    except AqlError:
        return None


_FLOW_TEMPLATES = {
    SxQcFlowCheck.FLOW_INLINE: 'san_xuat/qc_flow_inline.html',
    SxQcFlowCheck.FLOW_ENDLINE: 'san_xuat/qc_flow_endline.html',
    SxQcFlowCheck.FLOW_PREAUDIT: 'san_xuat/qc_flow_preaudit.html',
}


def _edit(request, *, flow: str, check: SxQcFlowCheck | None):
    meta = flow_meta(flow)
    locked = check is not None and check.status == SxQcFlowCheck.STATUS_DONE
    mo_hint = check.production_order if check is not None else _mo_from_request(request)
    if request.method == 'POST' and not locked:
        if not _can_write(request.user):
            messages.error(request, 'Bạn không có quyền sửa phiếu QC.')
            if check is None:
                return redirect('san_xuat:qc_flow_list', flow=flow)
            return redirect('san_xuat:qc_flow_detail', flow=flow, pk=check.pk)
        form = QcFlowCheckForm(request.POST, flow=flow, mo=mo_hint)
        action = (request.POST.get('action') or 'draft').strip()
        if action not in {'draft', 'save', 'pass', 'fail'}:
            action = 'draft'
        if form.is_valid():
            try:
                saved = save_flow_check(
                    flow=flow,
                    check=check,
                    cleaned=form.cleaned_data,
                    defect_rows=parse_defect_rows(request.POST),
                    size_rows=parse_size_rows(request.POST),
                    action=action,
                    user=request.user,
                )
            except QcError as exc:
                messages.error(request, str(exc))
            else:
                if saved.status == SxQcFlowCheck.STATUS_DONE and saved.result == SxQcFlowCheck.RESULT_PASS:
                    messages.success(request, f'{saved.code} đã chốt Đạt.')
                elif saved.result == SxQcFlowCheck.RESULT_FAIL:
                    messages.success(request, f'{saved.code} đã chốt Không đạt.')
                elif saved.result == SxQcFlowCheck.RESULT_NOTED:
                    messages.success(request, f'Đã ghi {saved.code}.')
                else:
                    messages.success(request, f'Đã lưu nháp {saved.code}.')
                return redirect('san_xuat:qc_flow_detail', flow=flow, pk=saved.pk)
        else:
            messages.error(request, 'Chưa lưu được — kiểm tra các ô bắt buộc.')
        defect_rows = _pad_defects(parse_defect_rows(request.POST))
        mo_hint = _mo_for_sheet(form, mo_hint)
    else:
        initial = _initial_from_check(check) if check is not None else _initial_from_mo(mo_hint, flow)
        form = QcFlowCheckForm(initial=initial, flow=flow, mo=mo_hint)
        defect_rows = blank_defect_slots(check)
        if locked:
            for field in form.fields.values():
                field.disabled = True

    size_rows = size_form_rows(mo_hint, check, request.POST if request.method == 'POST' and not locked else None)
    lot = mo_hint.qty if mo_hint is not None else 0
    if form.is_bound and form.data.get('qty_lot'):
        lot = form.data.get('qty_lot')
    elif check is not None and flow == SxQcFlowCheck.FLOW_PREAUDIT:
        lot = check.qty_lot
    recent_inline = []
    if flow == SxQcFlowCheck.FLOW_INLINE and mo_hint is not None:
        recent_qs = SxQcFlowCheck.objects.filter(
            is_demo=False,
            flow=SxQcFlowCheck.FLOW_INLINE,
            production_order=mo_hint,
        )
        if check is not None:
            recent_qs = recent_qs.exclude(pk=check.pk)
        recent_inline = list(recent_qs.order_by('-checked_on', '-pk')[:6])
    return render(request, _FLOW_TEMPLATES[flow], {
        **_perm_ctx(request),
        'flow': flow,
        'meta': meta,
        'form': form,
        'check': check,
        'order': mo_hint,
        'locked': locked,
        'defect_rows': defect_rows,
        'size_rows': size_rows,
        'defect_catalog': list(
            SxQcDefect.objects.filter(is_demo=False, is_active=True)
            .select_related('group')
            .order_by('group__name', 'name')
        ),
        'aql_preview': _aql_preview(lot) if flow == SxQcFlowCheck.FLOW_PREAUDIT else None,
        'aql_bands': aql_fixed_bands() if flow == SxQcFlowCheck.FLOW_PREAUDIT else [],
        'endline_pass': passed_endline(mo=mo_hint) if flow == SxQcFlowCheck.FLOW_ENDLINE and mo_hint is not None else None,
        'inline_stages': inline_stages_by_team() if flow == SxQcFlowCheck.FLOW_INLINE else {},
        'recent_inline': recent_inline,
        'can_write_qc': _can_write(request.user) and not locked,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_http_methods(['GET', 'POST'])
def qc_setup(request):
    denied = _guard(request)
    if denied:
        return denied
    if request.method == 'POST':
        if not _can_write(request.user):
            messages.error(request, 'Bạn không có quyền sửa danh mục lỗi.')
            return redirect('san_xuat:qc_setup')
        action = (request.POST.get('action') or '').strip()
        if action == 'add_group':
            code = (request.POST.get('group_code') or '').strip()
            name = (request.POST.get('group_name') or '').strip()
            if not code or not name:
                messages.error(request, 'Nhóm lỗi cần mã và tên.')
            elif SxQcDefectGroup.objects.filter(code=code).exists():
                messages.error(request, f'Mã nhóm {code} đã có.')
            else:
                SxQcDefectGroup.objects.create(code=code, name=name, is_active=True, is_demo=False)
                messages.success(request, f'Đã thêm nhóm {name}.')
        elif action == 'add_defect':
            code = (request.POST.get('defect_code') or '').strip()
            name = (request.POST.get('defect_name') or '').strip()
            group_id = (request.POST.get('defect_group') or '').strip()
            severity = (request.POST.get('defect_severity') or 'major').strip()
            if severity not in {'minor', 'major', 'critical'}:
                severity = 'major'
            group = SxQcDefectGroup.objects.filter(pk=group_id, is_demo=False).first() if group_id.isdigit() else None
            if not code or not name or group is None:
                messages.error(request, 'Mã lỗi cần mã, tên và nhóm.')
            elif SxQcDefect.objects.filter(code=code).exists():
                messages.error(request, f'Mã lỗi {code} đã có.')
            else:
                SxQcDefect.objects.create(
                    code=code, name=name, group=group, severity=severity, is_active=True, is_demo=False,
                )
                messages.success(request, f'Đã thêm lỗi {name}.')
        elif action == 'toggle_group':
            group = get_object_or_404(SxQcDefectGroup, pk=request.POST.get('pk'), is_demo=False)
            group.is_active = not group.is_active
            group.save(update_fields=['is_active'])
        elif action == 'toggle_defect':
            defect = get_object_or_404(SxQcDefect, pk=request.POST.get('pk'), is_demo=False)
            defect.is_active = not defect.is_active
            defect.save(update_fields=['is_active'])
        return redirect('san_xuat:qc_setup')
    return render(request, 'san_xuat/qc_setup.html', {
        **_perm_ctx(request),
        'groups': SxQcDefectGroup.objects.filter(is_demo=False).order_by('code'),
        'defects': SxQcDefect.objects.filter(is_demo=False).select_related('group').order_by('group__code', 'code'),
        'can_write_qc': _can_write(request.user),
    })
