from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

from hrm.menu_permissions import (
    user_can_create_menu,
    user_can_delete_menu,
    user_can_update_menu,
)
from hrm.module_permissions import (
    MODULE_DE_XUAT,
    MODULE_HO_TRO,
    user_can_access_module,
    user_can_create_module,
    user_can_delete_module,
    user_can_update_module,
)
from hrm.permissions import (
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    get_profile,
    is_department_head,
    is_director,
    is_division_head,
    user_role,
)

from .access import module_for_request, user_can_access_any_request_module
from .models import RequestTypeStepTemplate, ServiceRequest, ServiceRequestStep
from .workflow import get_accounting_department, get_procurement_department
from .workflow_it import get_it_department

_PROCUREMENT_QUEUE_STEP_CODES = frozenset({
    ServiceRequestStep.STEP_PROCUREMENT_QUOTE,
    ServiceRequestStep.STEP_PURCHASE,
    ServiceRequestStep.STEP_ADVANCE,
})


def is_procurement_staff(user) -> bool:
    """Nhân viên Thu mua được phép xử lý hàng đợi mua sắm."""
    if not user or not user.is_authenticated:
        return False
    return get_procurement_staff_candidates().filter(pk=user.pk).exists()


def _is_procurement_queue_step(step: ServiceRequestStep) -> bool:
    procurement_dept = get_procurement_department()
    if not procurement_dept or not step.target_department_id:
        return False
    return (
        step.step_code in _PROCUREMENT_QUEUE_STEP_CODES
        and step.target_department_id == procurement_dept.id
        and step.assignee_rule == RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE
    )


def get_step_waiting_message(step: ServiceRequestStep | None) -> str:
    """Thông báo cho người xem nhưng không phải người xử lý bước hiện tại."""
    if not step:
        return ''
    if step.assignee_id:
        profile = getattr(step.assignee, 'profile', None)
        name = profile.full_name if profile and profile.full_name else step.assignee.username
        return f'Đang chờ {name} xử lý bước này.'
    if step.step_code == ServiceRequestStep.STEP_PROCUREMENT_QUOTE:
        return 'Đang chờ nhân viên Thu mua báo giá nhà cung cấp (NCC).'
    if step.step_code == ServiceRequestStep.STEP_ACCOUNTANT:
        return 'Đang chờ Kế toán duyệt chi phí.'
    if step.step_code == ServiceRequestStep.STEP_DIRECTOR:
        return 'Đang chờ Giám đốc duyệt chi phí.'
    if step.target_department_id:
        return f'Đang chờ phòng {step.target_department.name} tiếp nhận.'
    return 'Đang chờ người xử lý tiếp theo.'


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
    if not user_can_update_menu(user, MODULE_DE_XUAT, 'catalog'):
        return False
    return _user_in_department(user, get_procurement_department())


def can_create_request(user, flow_tab) -> bool:
    from .access import module_for_flow
    module = module_for_flow(flow_tab)
    return user_can_create_menu(user, module, 'create')


def can_handle_request_workflow(user, request_obj: ServiceRequest) -> bool:
    return user_can_update_menu(user, module_for_request(request_obj), 'pending')


def can_cancel_own_request(user, request_obj: ServiceRequest) -> bool:
    if request_obj.requester_id != user.id:
        return False
    return user_can_delete_menu(user, module_for_request(request_obj), 'my')


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
                ServiceRequestStep.STEP_DEPARTMENT_HEAD,
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
    if step.step_code == ServiceRequestStep.STEP_DEPARTMENT_HEAD and is_department_head(user):
        return True
    if step.assignee_id:
        return step.assignee_id == user.id
    if step.assignee_rule == RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE:
        if _is_procurement_queue_step(step):
            return is_procurement_staff(user)
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
    if step.assignee_id:
        return False
    # GĐ (hoặc handler) tiếp nhận bước cấp trên khi tạo phiếu không gán được manager
    if step.step_code in {
        ServiceRequestStep.STEP_DIVISION_HEAD,
        ServiceRequestStep.STEP_DEPARTMENT_HEAD,
        ServiceRequestStep.STEP_TEAM_LEADER,
    } and step.assignee_rule == RequestTypeStepTemplate.RULE_DIRECT_MANAGER:
        return True
    return step.assignee_rule in {
        RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        RequestTypeStepTemplate.RULE_DIRECTOR,
    }


def involved_requests_for_user(user):
    """Yêu cầu user tham gia (duyệt/xử lý) nhưng không phải người gửi — để theo dõi tiến trình."""
    if not user_can_access_any_request_module(user):
        return ServiceRequest.objects.none()

    profile = get_profile(user)
    dept_id = profile.department_id if profile else None

    related = Q(steps__assignee=user) | Q(goods_receiver=user)
    if dept_id:
        related |= Q(steps__target_department_id=dept_id)
    if is_director(user):
        related |= Q(
            steps__step_code__in=(
                ServiceRequestStep.STEP_DIRECTOR,
                ServiceRequestStep.STEP_DEPARTMENT_HEAD,
                ServiceRequestStep.STEP_DIVISION_HEAD,
            ),
        )
        related |= Q(
            steps__target_department__isnull=False,
            steps__step_code__in=(
                ServiceRequestStep.STEP_PROCUREMENT_QUOTE,
                ServiceRequestStep.STEP_ACCOUNTANT,
                ServiceRequestStep.STEP_ADVANCE,
                ServiceRequestStep.STEP_PURCHASE,
            ),
        )

    return (
        ServiceRequest.objects.filter(related)
        .exclude(requester=user)
        .distinct()
        .select_related('request_type', 'requester', 'requester__profile')
        .prefetch_related('steps__assignee__profile', 'steps__target_department')
        .order_by('-updated_at', '-created_at')
    )


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

    procurement_dept = get_procurement_department()
    procurement_dept_id = procurement_dept.id if procurement_dept else None
    not_procurement_queue = ~Q(step_code__in=_PROCUREMENT_QUEUE_STEP_CODES)

    filters = Q(assignee=user)
    if dept_id:
        filters |= Q(
            assignee__isnull=True,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department_id=dept_id,
        ) & not_procurement_queue
    if procurement_dept_id and is_procurement_staff(user):
        filters |= Q(
            assignee__isnull=True,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department_id=procurement_dept_id,
            step_code__in=_PROCUREMENT_QUEUE_STEP_CODES,
        )
    if is_director(user):
        filters |= Q(step_code=ServiceRequestStep.STEP_DIVISION_HEAD)
        filters |= Q(step_code=ServiceRequestStep.STEP_DEPARTMENT_HEAD)
        filters |= Q(
            assignee__isnull=True,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        ) & not_procurement_queue
        filters |= Q(
            step_code=ServiceRequestStep.STEP_DIRECTOR,
        ) & (Q(assignee=user) | Q(assignee__isnull=True))
    elif is_division_head(user):
        filters |= Q(
            step_code=ServiceRequestStep.STEP_DIVISION_HEAD,
            assignee=user,
        )
    elif is_department_head(user):
        filters |= Q(
            step_code=ServiceRequestStep.STEP_DEPARTMENT_HEAD,
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


def _procurement_staff_username_whitelist() -> list[str]:
    raw = (getattr(settings, 'PROCUREMENT_STAFF_USERNAMES', '') or '').strip()
    if not raw:
        return []
    return [part.strip().lower() for part in raw.split(',') if part.strip()]


def get_procurement_staff_candidates():
    """Nhân viên Thu mua — whitelist settings hoặc phòng HCNS / quyền sửa Đề xuất."""
    base_qs = User.objects.filter(
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile')

    whitelist = _procurement_staff_username_whitelist()
    if whitelist:
        name_filter = Q()
        for username in whitelist:
            name_filter |= Q(username__iexact=username)
        candidates = _procurement_staff_from_queryset(base_qs.filter(name_filter))
        if candidates.exists():
            return candidates

    dept = get_procurement_department()
    if dept:
        candidates = _procurement_staff_from_queryset(
            base_qs.filter(profile__department=dept),
        )
        if candidates.exists():
            return candidates

    edit_pks = [
        user.pk for user in base_qs
        if user_can_update_module(user, MODULE_DE_XUAT)
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
