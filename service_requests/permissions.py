from hrm.module_permissions import MODULE_SERVICE_REQUESTS, user_can_access_module
from hrm.permissions import get_profile

from .models import RequestTypeStepTemplate, ServiceRequest, ServiceRequestStep


def _has_module_access(user) -> bool:
    return user_can_access_module(user, MODULE_SERVICE_REQUESTS)


def can_view_request(user, request_obj: ServiceRequest) -> bool:
    if not _has_module_access(user):
        return False
    if request_obj.requester_id == user.id:
        return True
    if request_obj.steps.filter(assignee_id=user.id).exists():
        return True
    profile = get_profile(user)
    if not profile or not profile.department_id:
        return False
    return request_obj.steps.filter(target_department_id=profile.department_id).exists()


def can_handle_step(user, step: ServiceRequestStep) -> bool:
    if not _has_module_access(user):
        return False
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        return False
    if step.assignee_id:
        return step.assignee_id == user.id
    if step.assignee_rule == RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE:
        profile = get_profile(user)
        return bool(
            profile
            and profile.department_id
            and step.target_department_id == profile.department_id,
        )
    return False


def can_claim_step(user, step: ServiceRequestStep) -> bool:
    if not can_handle_step(user, step):
        return False
    if step.assignee_id:
        return False
    return step.assignee_rule == RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE


def pending_steps_for_user(user):
    """Bước chờ user xử lý (đã gán hoặc queue phòng ban)."""
    if not _has_module_access(user):
        return ServiceRequestStep.objects.none()

    profile = get_profile(user)
    dept_id = profile.department_id if profile else None

    qs = ServiceRequestStep.objects.filter(
        request__status=ServiceRequest.STATUS_IN_PROGRESS,
        status__in=ServiceRequestStep.OPEN_HANDLER_STATUSES,
    ).select_related(
        'request', 'request__requester', 'request__requester__profile',
        'target_department', 'assignee', 'assignee__profile',
    )

    from django.db.models import Q
    filters = Q(assignee=user)
    if dept_id:
        filters |= Q(
            assignee__isnull=True,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department_id=dept_id,
        )
    return qs.filter(filters).order_by('-request__created_at', 'step_order')
