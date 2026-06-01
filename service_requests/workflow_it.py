"""Quy trình sửa chữa IT — không duyệt TL/BP, thẳng hàng đợi IT."""

from decimal import Decimal

from django.db import transaction

from .models import RequestType, RequestTypeStepTemplate, ServiceRequest, ServiceRequestStep
from .workflow import (
    _create_step,
    _log_step_opened,
    _maybe_complete_request,
    get_department_by_patterns,
    log_action,
)


def get_it_department():
    return get_department_by_patterns('IT', 'cntt', 'công nghệ', 'cong nghe')


def get_it_repair_request_type():
    return RequestType.objects.filter(
        is_active=True,
        code=RequestType.CODE_IT_REPAIR,
    ).first()


def _build_it_repair_steps(service_request):
    it_dept = get_it_department()
    repair_step = _create_step(
        service_request,
        step_order=1,
        step_code=ServiceRequestStep.STEP_IT_REPAIR,
        name='IT xử lý sự cố',
        step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
        assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        target_department=it_dept,
        depends_on=None,
    )
    _create_step(
        service_request,
        step_order=2,
        step_code=ServiceRequestStep.STEP_REQUESTER_CONFIRM,
        name='Người gửi xác nhận',
        step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
        assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
        depends_on=repair_step,
    )
    return [repair_step]


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
    )

    steps = _build_it_repair_steps(service_request)
    if not steps:
        raise ValueError('Không thể tạo quy trình IT.')

    log_action(service_request, actor=requester, action='created', message='Gửi yêu cầu sửa chữa IT')
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
    if not _maybe_complete_request(request_obj, actor=actor):
        for child in unlocked:
            _log_step_opened(request_obj, actor, child)
    return request_obj


@transaction.atomic
def complete_requester_confirmation(step, *, actor, note=''):
    if step.step_code != ServiceRequestStep.STEP_REQUESTER_CONFIRM:
        raise ValueError('Bước không phải xác nhận người gửi.')
    if step.request.requester_id != actor.id:
        raise ValueError('Chỉ người gửi mới xác nhận được.')
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể hoàn thành.')

    from .workflow import _complete_step

    _complete_step(step, actor=actor, note=note or 'Người gửi xác nhận đã sửa xong')
    _maybe_complete_request(step.request, actor=actor)
    return step.request
