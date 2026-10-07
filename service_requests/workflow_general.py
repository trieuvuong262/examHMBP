"""Quy trình đề xuất chung (phi mua-hàng) — Tổ trưởng → Trưởng BP → (duyệt cấp cao) → kết thúc.

Dùng chung khung duyệt cơ bản theo cấp quản lý của người gửi (phương án 1a).
Nếu có số tiền (thanh toán/tạm ứng...) vượt ngưỡng thì chèn thêm bước Kế toán/Giám đốc.
"""

from decimal import Decimal

from django.db import transaction

from .models import (
    RequestType,
    RequestTypeStepTemplate,
    ServiceRequest,
    ServiceRequestStep,
)
from .workflow import (
    AMOUNT_ACCOUNTING_MIN,
    AMOUNT_DIRECTOR_MIN,
    _create_step,
    _log_step_opened,
    _needs_department_head_step,
    _needs_division_head_step,
    _needs_team_leader_step,
    find_department_head_manager,
    find_division_head_manager,
    find_team_leader,
    get_accounting_department,
    log_action,
)


def get_general_request_type():
    return RequestType.objects.filter(
        is_active=True,
        code=RequestType.CODE_GENERAL_PROPOSAL,
    ).first()


def _amount_tier(amount):
    if amount is None or amount < AMOUNT_ACCOUNTING_MIN:
        return ServiceRequest.TIER_NONE
    if amount >= AMOUNT_DIRECTOR_MIN:
        return ServiceRequest.TIER_DIRECTOR
    return ServiceRequest.TIER_ACCOUNTANT


def _final_step_spec(service_request):
    """(tên bước kết thúc, phòng ban xử lý) theo loại đề xuất."""
    from .workflow import get_department_by_patterns, get_procurement_department

    subtype = service_request.request_subtype
    if subtype == ServiceRequest.SUBTYPE_REPAIR:
        return 'Bộ phận kỹ thuật xử lý', get_department_by_patterns(
            'IT', 'cntt', 'công nghệ', 'cong nghe', 'bảo trì', 'bao tri',
        )
    if subtype in (ServiceRequest.SUBTYPE_HR, ServiceRequest.SUBTYPE_CANDIDATE):
        name = 'HCNS tiếp nhận tuyển dụng' if subtype == ServiceRequest.SUBTYPE_CANDIDATE else 'HCNS xử lý'
        return name, get_department_by_patterns(
            'hành chính nhân sự', 'hcns', 'nhân sự', 'nhan su',
        )
    if subtype == ServiceRequest.SUBTYPE_ACCOUNT:
        return 'IT cấp phát', get_department_by_patterns(
            'IT', 'cntt', 'công nghệ', 'cong nghe',
        )
    if subtype == ServiceRequest.SUBTYPE_PAYMENT:
        return 'Kế toán xử lý chi', get_accounting_department()
    return 'Bộ phận phụ trách xử lý', get_procurement_department()


def _build_general_steps(service_request):
    requester = service_request.requester
    steps = []
    order = 1
    previous = None

    if _needs_team_leader_step(requester):
        step = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_TEAM_LEADER,
            name='Tổ trưởng duyệt',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
            assignee=find_team_leader(requester),
            depends_on=previous,
        )
        steps.append(step)
        previous = step
        order += 1

    if _needs_division_head_step(requester):
        step = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_DIVISION_HEAD,
            name='Trưởng bộ phận duyệt',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
            assignee=find_division_head_manager(requester),
            depends_on=previous,
        )
        steps.append(step)
        previous = step
        order += 1

    if _needs_department_head_step(requester):
        step = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_DEPARTMENT_HEAD,
            name='Trưởng phòng duyệt',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
            assignee=find_department_head_manager(requester),
            depends_on=previous,
        )
        steps.append(step)
        previous = step
        order += 1

    # Duyệt cấp cao theo số tiền (nếu loại đề xuất có số tiền).
    tier = _amount_tier(service_request.payment_amount)
    service_request.approval_tier = tier
    if tier == ServiceRequest.TIER_DIRECTOR:
        step = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_DIRECTOR,
            name='Giám đốc duyệt chi phí',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECTOR,
            depends_on=previous,
        )
        steps.append(step)
        previous = step
        order += 1
    elif tier == ServiceRequest.TIER_ACCOUNTANT:
        step = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_ACCOUNTANT,
            name='Kế toán duyệt chi phí',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department=get_accounting_department(),
            depends_on=previous,
        )
        steps.append(step)
        previous = step
        order += 1

    # Bước thực hiện cuối theo loại.
    final_name, final_dept = _final_step_spec(service_request)
    final_step = _create_step(
        service_request,
        step_order=order,
        step_code=ServiceRequestStep.STEP_GENERAL_EXECUTION,
        name=final_name,
        step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
        assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        target_department=final_dept,
        depends_on=previous,
    )
    steps.append(final_step)
    return steps


@transaction.atomic
def create_general_request_with_steps(
    *,
    requester,
    request_type,
    subtype,
    title,
    description,
    payment_amount=None,
    extra_data=None,
):
    service_request = ServiceRequest.objects.create(
        requester=requester,
        request_type=request_type,
        request_subtype=subtype,
        title=title,
        description=description,
        payment_amount=payment_amount,
        extra_data=extra_data or {},
    )

    steps = _build_general_steps(service_request)
    if not steps:
        raise ValueError('Không thể tạo quy trình xử lý.')
    service_request.save(update_fields=['approval_tier', 'updated_at'])

    log_action(
        service_request,
        actor=requester,
        action='created',
        message=f'Gửi đề xuất: {service_request.subtype_label}',
    )
    first_active = service_request.steps.exclude(
        status=ServiceRequestStep.STATUS_SKIPPED,
    ).order_by('step_order').first()
    if first_active:
        _log_step_opened(service_request, requester, first_active)

    return service_request


def preview_flow(requester, subtype):
    """Các bước dự kiến cho người gửi + loại đề xuất — hiển thị ở màn hình tạo.

    Dùng đúng các điều kiện khi tạo bước thật (_needs_*, ngưỡng tiền, _final_step_spec)
    để khung quy trình không lệch với luồng thực tế.

    Mỗi bước: {'label', 'note', 'kind': approval|execution, 'tier': ''|accountant|director,
    'advance': bool}. Bước có ``tier`` chỉ áp dụng khi số tiền rơi vào ngưỡng đó.
    """
    from types import SimpleNamespace

    from hrm.permissions import get_profile

    from .workflow import department_has_department_heads, get_procurement_department

    steps = []

    def add(label, note='', kind='approval', tier='', advance=False):
        steps.append({'label': label, 'note': note, 'kind': kind, 'tier': tier, 'advance': advance})

    if _needs_team_leader_step(requester):
        add('Tổ trưởng duyệt')
    if _needs_division_head_step(requester):
        note = 'Chỉ định nhân viên Thu mua' if subtype == ServiceRequest.SUBTYPE_PURCHASE else ''
        add('Trưởng bộ phận duyệt', note)
    if _needs_department_head_step(requester):
        profile = get_profile(requester)
        has_heads = bool(profile and profile.department_id and department_has_department_heads(profile.department))
        add('Trưởng phòng duyệt' if has_heads else 'Giám đốc duyệt (thay Trưởng phòng)')

    acc_min = f'{AMOUNT_ACCOUNTING_MIN:,.0f}'.replace(',', '.')
    dir_min = f'{AMOUNT_DIRECTOR_MIN:,.0f}'.replace(',', '.')

    if subtype == ServiceRequest.SUBTYPE_PURCHASE:
        procurement = get_procurement_department()
        add('Thu mua kiểm tra giá & NCC', procurement.name if procurement else '', kind='execution')
        add('Kế toán duyệt chi phí', f'Tổng NCC từ {acc_min} đến dưới {dir_min} VNĐ', tier='accountant')
        add('Giám đốc duyệt chi phí', f'Tổng NCC từ {dir_min} VNĐ', tier='director')
        add('Tạm ứng', 'Khi chọn cần tạm ứng', kind='execution', advance=True)
        add('Thu mua đặt hàng', kind='execution')
        add('Xác nhận nhận hàng', 'Người nhận hàng', kind='execution')
        return steps

    if subtype == ServiceRequest.SUBTYPE_PAYMENT:
        add('Kế toán duyệt chi phí', f'Số tiền từ {acc_min} đến dưới {dir_min} VNĐ', tier='accountant')
        add('Giám đốc duyệt chi phí', f'Số tiền từ {dir_min} VNĐ', tier='director')

    final_name, final_dept = _final_step_spec(SimpleNamespace(request_subtype=subtype))
    add(final_name, final_dept.name if final_dept else '', kind='execution')
    return steps


def approval_thresholds():
    return {
        'accountant_min': int(AMOUNT_ACCOUNTING_MIN),
        'director_min': int(AMOUNT_DIRECTOR_MIN),
    }
