"""Hàng đợi xử lý Hỗ trợ kỹ thuật — trong module Quản lý thiết bị."""

from django.contrib.auth.models import User
from django.db.models import Q

from equipment.scope import SCOPE_IT, SCOPE_PRODUCTION
from equipment.services.device_categories import category_codes_for_profile
from hrm.module_permissions import MODULE_EQUIPMENT, user_can_access_module
from hrm.permissions import get_profile
from service_requests.models import RequestType, RequestTypeStepTemplate, ServiceRequest, ServiceRequestStep
from service_requests.workflow_it import get_it_department


def _has_equipment_access(user) -> bool:
    return user_can_access_module(user, MODULE_EQUIPMENT)


def can_handle_it_repair_step(user, step: ServiceRequestStep) -> bool:
    """IT xử lý sự cố — quyền module Quản lý thiết bị + thuộc phòng IT."""
    if not _has_equipment_access(user):
        return False
    if step.step_code != ServiceRequestStep.STEP_IT_REPAIR:
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


def can_claim_it_repair_step(user, step: ServiceRequestStep) -> bool:
    if not can_handle_it_repair_step(user, step):
        return False
    if step.assignee_id:
        return False
    return step.assignee_rule == RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE


def _filter_steps_for_equipment_scope(qs, equipment_scope: str | None):
    if not equipment_scope:
        return qs

    explicit = Q(request__repair_equipment_scope=equipment_scope)
    legacy = Q(request__repair_equipment_scope='')
    if equipment_scope == SCOPE_PRODUCTION:
        codes = category_codes_for_profile('machine')
        if codes:
            legacy &= Q(request__equipment__category__in=codes)
        else:
            legacy = Q(pk__in=[])
    else:
        codes = category_codes_for_profile('it')
        if codes:
            legacy &= Q(request__equipment__isnull=True) | Q(request__equipment__category__in=codes)
        else:
            legacy &= Q(request__equipment__isnull=True)
    return qs.filter(explicit | legacy)


def pending_it_repair_steps_for_user(user, equipment_scope: str | None = None):
    """Bước IT xử lý sự cố chờ user (module thiết bị)."""
    if not _has_equipment_access(user):
        return ServiceRequestStep.objects.none()

    profile = get_profile(user)
    dept_id = profile.department_id if profile else None

    qs = ServiceRequestStep.objects.filter(
        step_code=ServiceRequestStep.STEP_IT_REPAIR,
        request__status=ServiceRequest.STATUS_IN_PROGRESS,
        request__request_type__code=RequestType.CODE_IT_REPAIR,
        status__in=ServiceRequestStep.OPEN_HANDLER_STATUSES,
    ).select_related(
        'request',
        'request__requester',
        'request__requester__profile',
        'request__equipment',
        'target_department',
        'assignee',
        'assignee__profile',
    )

    filters = Q(assignee=user)
    if dept_id:
        filters |= Q(
            assignee__isnull=True,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department_id=dept_id,
        )
    qs = qs.filter(filters)
    qs = _filter_steps_for_equipment_scope(qs, equipment_scope)
    return qs.order_by('-request__priority', '-request__created_at', 'step_order')


def get_it_staff_with_equipment_access():
    """Nhân viên IT có quyền module Quản lý thiết bị."""
    dept = get_it_department()
    if not dept:
        return User.objects.none()
    qs = User.objects.filter(
        profile__department=dept,
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile').order_by('profile__full_name', 'username')
    return qs.filter(
        pk__in=[user.pk for user in qs if user_can_access_module(user, MODULE_EQUIPMENT)],
    )
