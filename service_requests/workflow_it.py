"""Quy trình Hỗ trợ kỹ thuật — Tổ trưởng (nếu có) → IT xử lý → hoàn thành."""

from django.db import transaction

from .models import RequestType, RequestTypeStepTemplate, ServiceRequest, ServiceRequestStep
from .workflow import (
    _create_step,
    _log_step_opened,
    _maybe_complete_request,
    find_team_leader,
    get_department_by_patterns,
    log_action,
    _needs_team_leader_step,
)


def get_it_department():
    return get_department_by_patterns('IT', 'cntt', 'công nghệ', 'cong nghe')


def get_it_repair_request_type():
    return RequestType.objects.filter(
        is_active=True,
        code=RequestType.CODE_IT_REPAIR,
    ).first()


def apply_it_repair_completion_side_effects(service_request, *, repair_cost=None):
    """Cập nhật thiết bị + nhật ký bảo trì khi IT hoàn thành."""
    if not service_request.equipment_id:
        return
    from equipment.models import Device, MaintenanceLog

    dev = service_request.equipment
    dev.status = Device.STATUS_ACTIVE
    dev.save(update_fields=['status', 'updated_at'])

    logs = MaintenanceLog.objects.filter(
        device=dev,
        service_request=service_request,
        is_resolved=False,
    )
    update_kwargs = {'is_resolved': True}
    if repair_cost is not None:
        update_kwargs['cost'] = repair_cost
    logs.update(**update_kwargs)


def _build_it_repair_steps(service_request):
    requester = service_request.requester
    it_dept = get_it_department()
    order = 1
    previous = None
    first_active = None

    if _needs_team_leader_step(requester):
        tl = find_team_leader(requester)
        tl_step = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_TEAM_LEADER,
            name='Tổ trưởng duyệt',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
            assignee=tl,
            depends_on=previous,
        )
        previous = tl_step
        order += 1
        if not first_active:
            first_active = tl_step

    repair_step = _create_step(
        service_request,
        step_order=order,
        step_code=ServiceRequestStep.STEP_IT_REPAIR,
        name='IT xử lý sự cố',
        step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
        assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        target_department=it_dept,
        depends_on=previous,
    )
    if not first_active:
        first_active = repair_step
    return [first_active] if first_active else [repair_step]


@transaction.atomic
def create_it_repair_request(
    *,
    requester,
    request_type,
    title,
    description,
    incident_category,
    priority,
    location_text='',
    equipment_label='',
    equipment_serial='',
    blocks_work=False,
    equipment=None,
):
    service_request = ServiceRequest.objects.create(
        requester=requester,
        request_type=request_type,
        title=title,
        description=description,
        incident_category=incident_category,
        priority=priority,
        location_text=location_text,
        equipment_label=equipment_label,
        equipment_serial=equipment_serial,
        blocks_work=blocks_work,
        equipment=equipment,
    )

    steps = _build_it_repair_steps(service_request)
    if not steps:
        raise ValueError('Không thể tạo quy trình IT.')

    log_action(service_request, actor=requester, action='created', message='Gửi yêu cầu hỗ trợ kỹ thuật')
    first_active = service_request.steps.exclude(
        status=ServiceRequestStep.STATUS_SKIPPED,
    ).order_by('step_order').first()
    if first_active:
        _log_step_opened(service_request, requester, first_active)

    return service_request


@transaction.atomic
def complete_it_repair_step(
    step,
    *,
    actor,
    note,
    repair_cost=None,
    expected_return_date=None,
):
    if step.step_code != ServiceRequestStep.STEP_IT_REPAIR:
        raise ValueError('Bước không phải xử lý IT.')
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể hoàn thành.')

    request_obj = step.request
    update_fields = ['updated_at']
    if repair_cost is not None:
        request_obj.repair_cost = repair_cost
        update_fields.append('repair_cost')
    if expected_return_date is not None:
        request_obj.expected_return_date = expected_return_date
        update_fields.append('expected_return_date')
    if len(update_fields) > 1:
        request_obj.save(update_fields=update_fields)

    from .workflow import _complete_step

    unlocked = _complete_step(step, actor=actor, note=note)
    completed = _maybe_complete_request(request_obj, actor=actor)
    if completed:
        apply_it_repair_completion_side_effects(request_obj, repair_cost=repair_cost)
    elif unlocked:
        for child in unlocked:
            _log_step_opened(request_obj, actor, child)
    return request_obj
