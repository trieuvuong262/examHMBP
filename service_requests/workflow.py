"""Quy trình yêu cầu — sinh bước, gán người xử lý, mở bước kế tiếp."""

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from hrm.permissions import ROLE_DIVISION_HEAD, ROLE_TEAM_LEADER, get_profile

from .models import (
    RequestType,
    RequestTypeStepTemplate,
    ServiceRequest,
    ServiceRequestLog,
    ServiceRequestStep,
)


def find_direct_manager(user):
    """Tìm cấp trên trực tiếp — ưu tiên Trưởng BP, sau đó Tổ trưởng."""
    if not user or not user.is_authenticated:
        return None

    managers = User.objects.filter(
        profile__subordinates=user,
        is_active=True,
        profile__is_employed=True,
    ).select_related('profile')

    for role in (ROLE_DIVISION_HEAD, ROLE_TEAM_LEADER):
        manager = managers.filter(profile__role=role).order_by('profile__full_name', 'username').first()
        if manager:
            return manager

    return managers.order_by('profile__full_name', 'username').first()


def _initial_step_status(depends_on_step):
    if depends_on_step is None:
        return ServiceRequestStep.STATUS_PENDING
    if depends_on_step.status == ServiceRequestStep.STATUS_COMPLETED:
        return ServiceRequestStep.STATUS_PENDING
    return ServiceRequestStep.STATUS_BLOCKED


def _resolve_assignee(template, requester):
    if template.assignee_rule == RequestTypeStepTemplate.RULE_DIRECT_MANAGER:
        return find_direct_manager(requester)
    return None


def log_action(request_obj, *, actor, action, message='', step=None):
    ServiceRequestLog.objects.create(
        request=request_obj,
        step=step,
        actor=actor,
        action=action,
        message=message,
    )


@transaction.atomic
def create_request_with_steps(*, requester, request_type, title, description, estimated_cost=None):
    service_request = ServiceRequest.objects.create(
        requester=requester,
        request_type=request_type,
        title=title,
        description=description,
        estimated_cost=estimated_cost,
    )

    templates = list(
        request_type.step_templates.select_related('target_department').order_by('step_order'),
    )
    if not templates:
        raise ValueError('Loại yêu cầu chưa có quy trình xử lý.')

    previous_step = None
    for template in templates:
        depends_on = previous_step
        status = _initial_step_status(depends_on)
        assignee = _resolve_assignee(template, requester) if status == ServiceRequestStep.STATUS_PENDING else None

        step = ServiceRequestStep.objects.create(
            request=service_request,
            template=template,
            step_order=template.step_order,
            name=template.name,
            step_kind=template.step_kind,
            assignee_rule=template.assignee_rule,
            target_department=template.target_department,
            assignee=assignee,
            depends_on=depends_on,
            status=status,
        )
        previous_step = step

    log_action(
        service_request,
        actor=requester,
        action='created',
        message='Gửi yêu cầu',
    )
    first_step = service_request.steps.order_by('step_order').first()
    if first_step and first_step.assignee:
        log_action(
            service_request,
            actor=requester,
            action='assigned',
            message=f'Chuyển bước 1 → {first_step.assignee.username}',
            step=first_step,
        )
    elif first_step and first_step.target_department:
        log_action(
            service_request,
            actor=requester,
            action='queued',
            message=f'Chuyển bước 1 → phòng {first_step.target_department.name}',
            step=first_step,
        )

    return service_request


def unlock_next_steps(completed_step):
    """Mở các bước phụ thuộc khi bước trước hoàn thành."""
    unlocked = []
    requester = completed_step.request.requester
    for child in ServiceRequestStep.objects.filter(
        request_id=completed_step.request_id,
        depends_on_id=completed_step.pk,
        status=ServiceRequestStep.STATUS_BLOCKED,
    ):
        child.status = ServiceRequestStep.STATUS_PENDING
        if child.assignee_rule == RequestTypeStepTemplate.RULE_DIRECT_MANAGER:
            child.assignee = find_direct_manager(requester)
        child.save(update_fields=['status', 'assignee'])
        unlocked.append(child)
    return unlocked


def _complete_step(step, *, actor, note=''):
    step.status = ServiceRequestStep.STATUS_COMPLETED
    step.note = note or step.note
    step.completed_at = timezone.now()
    step.save(update_fields=['status', 'note', 'completed_at'])

    log_action(
        step.request,
        actor=actor,
        action='step_completed',
        message=note or f'Hoàn thành: {step.name}',
        step=step,
    )
    return unlock_next_steps(step)


@transaction.atomic
def approve_step(step, *, actor, note=''):
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể duyệt.')

    unlocked = _complete_step(step, actor=actor, note=note)
    request_obj = step.request

    if not request_obj.steps.exclude(status=ServiceRequestStep.STATUS_COMPLETED).exists():
        request_obj.status = ServiceRequest.STATUS_COMPLETED
        request_obj.completed_at = timezone.now()
        request_obj.save(update_fields=['status', 'completed_at', 'updated_at'])
        log_action(request_obj, actor=actor, action='completed', message='Yêu cầu hoàn thành')
    else:
        for child in unlocked:
            if child.assignee:
                log_action(
                    request_obj,
                    actor=actor,
                    action='assigned',
                    message=f'Mở bước {child.step_order} → {child.assignee.username}',
                    step=child,
                )
            elif child.target_department:
                log_action(
                    request_obj,
                    actor=actor,
                    action='queued',
                    message=f'Mở bước {child.step_order} → phòng {child.target_department.name}',
                    step=child,
                )

    return request_obj


@transaction.atomic
def reject_step(step, *, actor, reason):
    if not reason.strip():
        raise ValueError('Vui lòng nhập lý do từ chối.')

    step.status = ServiceRequestStep.STATUS_REJECTED
    step.note = reason.strip()
    step.completed_at = timezone.now()
    step.save(update_fields=['status', 'note', 'completed_at'])

    request_obj = step.request
    request_obj.status = ServiceRequest.STATUS_REJECTED
    request_obj.save(update_fields=['status', 'updated_at'])

    log_action(
        request_obj,
        actor=actor,
        action='rejected',
        message=reason.strip(),
        step=step,
    )
    return request_obj


@transaction.atomic
def claim_step(step, *, actor):
    if step.assignee_rule != RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE:
        raise ValueError('Bước này không cần tiếp nhận.')
    if step.assignee_id:
        raise ValueError('Bước đã có người tiếp nhận.')
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể tiếp nhận.')

    step.assignee = actor
    if step.is_execution:
        step.status = ServiceRequestStep.STATUS_IN_PROGRESS
    step.save(update_fields=['assignee', 'status'])

    log_action(
        step.request,
        actor=actor,
        action='claimed',
        message=f'{actor.username} tiếp nhận bước {step.step_order}',
        step=step,
    )
    return step


@transaction.atomic
def complete_execution_step(step, *, actor, note):
    if not step.is_execution:
        raise ValueError('Bước này không phải bước thực hiện.')
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể hoàn thành.')

    return approve_step(step, actor=actor, note=note)


@transaction.atomic
def cancel_request(request_obj, *, actor):
    if request_obj.requester_id != actor.id:
        raise ValueError('Chỉ người gửi mới hủy được.')
    if request_obj.status != ServiceRequest.STATUS_IN_PROGRESS:
        raise ValueError('Yêu cầu không thể hủy.')

    first_step = request_obj.steps.order_by('step_order').first()
    if first_step and first_step.status != ServiceRequestStep.STATUS_PENDING:
        raise ValueError('Không thể hủy — yêu cầu đã được xử lý.')

    request_obj.status = ServiceRequest.STATUS_CANCELLED
    request_obj.save(update_fields=['status', 'updated_at'])
    log_action(request_obj, actor=actor, action='cancelled', message='Người gửi hủy yêu cầu')
    return request_obj


def get_active_request_type():
    return RequestType.objects.filter(
        is_active=True,
        code=RequestType.CODE_ASSET_PURCHASE,
    ).first()
