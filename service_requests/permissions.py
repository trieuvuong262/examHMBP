from decimal import Decimal

from django.contrib.auth.models import User

from hrm.module_permissions import MODULE_SERVICE_REQUESTS, user_can_access_module
from hrm.permissions import ROLE_DIRECTOR, get_profile, is_director

from .models import RequestTypeStepTemplate, ServiceRequest, ServiceRequestStep
from .workflow import get_accounting_department, get_procurement_department


def _has_module_access(user) -> bool:
    return user_can_access_module(user, MODULE_SERVICE_REQUESTS)


def _user_in_department(user, department) -> bool:
    if not department:
        return False
    profile = get_profile(user)
    return bool(profile and profile.department_id == department.id)


def can_view_pricing(user, request_obj: ServiceRequest) -> bool:
    """Chỉ Thu mua, Kế toán, Giám đốc xem được giá."""
    if not _has_module_access(user):
        return False
    if is_director(user):
        return True
    profile = get_profile(user)
    if not profile or not profile.department_id:
        return False
    procurement = get_procurement_department()
    accounting = get_accounting_department()
    return profile.department_id in {
        dept.id for dept in (procurement, accounting) if dept
    }


def can_manage_recurring_catalog(user) -> bool:
    """Thu mua quản lý danh mục hàng định kỳ."""
    if not _has_module_access(user):
        return False
    return _user_in_department(user, get_procurement_department())


def can_view_request(user, request_obj: ServiceRequest) -> bool:
    if not _has_module_access(user):
        return False
    if request_obj.requester_id == user.id:
        return True
    if request_obj.goods_receiver_id == user.id:
        return True
    if request_obj.steps.filter(assignee_id=user.id).exists():
        return True
    profile = get_profile(user)
    if not profile or not profile.department_id:
        return False
    if request_obj.steps.filter(target_department_id=profile.department_id).exists():
        return True
    if is_director(user):
        return request_obj.steps.filter(
            step_code=ServiceRequestStep.STEP_DIRECTOR,
        ).exists()
    return False


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
    if step.assignee_rule == RequestTypeStepTemplate.RULE_DIRECTOR:
        profile = get_profile(user)
        return bool(profile and profile.role == ROLE_DIRECTOR)
    return False


def can_claim_step(user, step: ServiceRequestStep) -> bool:
    if not can_handle_step(user, step):
        return False
    if step.assignee_id:
        return False
    return step.assignee_rule in {
        RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        RequestTypeStepTemplate.RULE_DIRECTOR,
    }


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
    if profile and profile.role == ROLE_DIRECTOR:
        filters |= Q(
            assignee__isnull=True,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECTOR,
            step_code=ServiceRequestStep.STEP_DIRECTOR,
        )
    return qs.filter(filters).order_by('-request__created_at', 'step_order')


def get_goods_receiver_candidates(request_obj: ServiceRequest):
    """Nhân viên có thể được gán nhận hàng — cùng phòng ban người gửi."""
    profile = get_profile(request_obj.requester)
    if not profile or not profile.department_id:
        return User.objects.none()
    return User.objects.filter(
        profile__department_id=profile.department_id,
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile').order_by('profile__full_name', 'username')
