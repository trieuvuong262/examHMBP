from django.contrib.auth.models import User

from hrm.module_permissions import (
    MODULE_DE_XUAT,
    MODULE_HO_TRO,
    user_can_access_module,
    user_can_edit_module,
)
from hrm.permissions import ROLE_DIRECTOR, get_profile, is_director, is_division_head, user_role

from .access import module_for_request, user_can_access_any_request_module
from .models import RequestTypeStepTemplate, ServiceRequest, ServiceRequestStep
from .workflow import get_accounting_department, get_procurement_department
from .workflow_it import get_it_department


def get_it_staff_candidates():
    """Nhân viên IT có quyền module Hỗ trợ kỹ thuật."""
    dept = get_it_department()
    if not dept:
        return User.objects.none()
    qs = User.objects.filter(
        profile__department=dept,
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile').order_by('profile__full_name', 'username')
    return qs.filter(
        pk__in=[user.pk for user in qs if user_can_access_module(user, MODULE_HO_TRO)],
    )


def _has_module_access(user, request_obj: ServiceRequest | None = None) -> bool:
    if request_obj is not None:
        return user_can_access_module(user, module_for_request(request_obj))
    return user_can_access_any_request_module(user)


def _user_in_department(user, department) -> bool:
    if not department:
        return False
    profile = get_profile(user)
    return bool(profile and profile.department_id == department.id)


def can_view_pricing(user, request_obj: ServiceRequest) -> bool:
    """Chỉ Thu mua, Kế toán, Giám đốc xem được giá."""
    if not user_can_access_module(user, MODULE_DE_XUAT):
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
    if not user_can_access_module(user, MODULE_DE_XUAT):
        return False
    return _user_in_department(user, get_procurement_department())


def can_view_request(user, request_obj: ServiceRequest) -> bool:
    if not _has_module_access(user, request_obj):
        return False
    if request_obj.requester_id == user.id:
        return True
    if request_obj.goods_receiver_id == user.id:
        return True
    if request_obj.steps.filter(assignee_id=user.id).exists():
        return True
    if is_director(user):
        if request_obj.steps.filter(
            step_code__in=(
                ServiceRequestStep.STEP_DIRECTOR,
                ServiceRequestStep.STEP_DIVISION_HEAD,
            ),
        ).exists():
            return True
    profile = get_profile(user)
    if not profile or not profile.department_id:
        return False
    if request_obj.steps.filter(target_department_id=profile.department_id).exists():
        return True
    if is_director(user):
        return request_obj.steps.filter(
            target_department__isnull=False,
            step_code__in=(
                ServiceRequestStep.STEP_PROCUREMENT_QUOTE,
                ServiceRequestStep.STEP_ACCOUNTANT,
                ServiceRequestStep.STEP_ADVANCE,
                ServiceRequestStep.STEP_PURCHASE,
            ),
        ).exists()
    return False


def can_handle_step(user, step: ServiceRequestStep) -> bool:
    if step.step_code == ServiceRequestStep.STEP_IT_REPAIR:
        return False
    if not _has_module_access(user, step.request):
        return False
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        return False
    if step.step_code == ServiceRequestStep.STEP_DIVISION_HEAD and is_division_head(user):
        return True
    if step.assignee_id:
        return step.assignee_id == user.id
    if step.assignee_rule == RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE:
        if is_director(user):
            return bool(step.target_department_id)
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
    if step.step_code == ServiceRequestStep.STEP_DIVISION_HEAD and is_director(user):
        return not step.assignee_id
    if step.assignee_id:
        return False
    return step.assignee_rule in {
        RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        RequestTypeStepTemplate.RULE_DIRECTOR,
    }


def pending_steps_for_user(user):
    """Bước chờ user xử lý (đã gán hoặc queue phòng ban)."""
    if not user_can_access_any_request_module(user):
        return ServiceRequestStep.objects.none()

    profile = get_profile(user)
    dept_id = profile.department_id if profile else None

    qs = ServiceRequestStep.objects.filter(
        request__status=ServiceRequest.STATUS_IN_PROGRESS,
        status__in=ServiceRequestStep.OPEN_HANDLER_STATUSES,
    ).exclude(
        step_code=ServiceRequestStep.STEP_IT_REPAIR,
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
    if is_director(user):
        filters |= Q(step_code=ServiceRequestStep.STEP_DIVISION_HEAD)
        filters |= Q(
            assignee__isnull=True,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        )
        filters |= Q(
            step_code=ServiceRequestStep.STEP_DIRECTOR,
        ) & (Q(assignee=user) | Q(assignee__isnull=True))
    elif user_role(user) == ROLE_DIVISION_HEAD:
        filters |= Q(
            step_code=ServiceRequestStep.STEP_DIVISION_HEAD,
            assignee=user,
        )
    return qs.filter(filters).order_by('-request__created_at', 'step_order')


def _procurement_staff_from_queryset(qs):
    pks = [
        user.pk for user in qs
        if user_can_access_module(user, MODULE_DE_XUAT)
    ]
    if not pks:
        return User.objects.none()
    return User.objects.filter(pk__in=pks).select_related('profile').order_by(
        'profile__full_name', 'username',
    )


def get_procurement_staff_candidates():
    """Nhân viên Thu mua — phòng Thu mua/HCNS có quyền Đề xuất; fallback: quyền sửa module."""
    base_qs = User.objects.filter(
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile')

    dept = get_procurement_department()
    if dept:
        candidates = _procurement_staff_from_queryset(
            base_qs.filter(profile__department=dept),
        )
        if candidates.exists():
            return candidates

    edit_pks = [
        user.pk for user in base_qs
        if user_can_edit_module(user, MODULE_DE_XUAT)
    ]
    if not edit_pks:
        return User.objects.none()
    return User.objects.filter(pk__in=edit_pks).select_related('profile').order_by(
        'profile__full_name', 'username',
    )


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
