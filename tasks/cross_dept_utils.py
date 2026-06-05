from django.contrib.auth.models import User
from django.db.models import Q

from hrm.module_permissions import MODULE_TASKS, user_can_access_module
from hrm.permissions import ROLE_DIRECTOR, ROLE_DIVISION_HEAD, get_profile, is_director

from .models import InternalProject, WorkTask


def get_department_task_users(department):
    """Nhân viên active trong phòng ban, có quyền module Công việc."""
    if department is None:
        return User.objects.none()
    qs = User.objects.filter(
        profile__department=department,
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile').order_by('profile__full_name', 'username')
    eligible_ids = [
        user.pk for user in qs
        if user_can_access_module(user, MODULE_TASKS) and user.profile.role != ROLE_DIRECTOR
    ]
    return User.objects.filter(pk__in=eligible_ids).select_related('profile')


def ensure_project_member(project, user):
    if user and not project.members.filter(pk=user.pk).exists():
        project.members.add(user)


def initial_cross_dept_step_status(depends_on_task, assignee_mode):
    if depends_on_task and depends_on_task.status != WorkTask.STATUS_COMPLETED:
        return WorkTask.STATUS_BLOCKED
    if assignee_mode == WorkTask.ASSIGNEE_DEPT_QUEUE:
        return WorkTask.STATUS_PENDING_CLAIM
    return WorkTask.STATUS_PENDING_ACK


def cross_dept_projects_for_user(user):
    """Dự án liên phòng ban user được xem trong danh sách."""
    profile = get_profile(user)
    qs = InternalProject.objects.filter(project_type=InternalProject.TYPE_CROSS_DEPT)
    filters = Q(owner=user) | Q(members=user)
    if is_director(user):
        return qs.distinct()
    if profile and profile.role == ROLE_DIVISION_HEAD and profile.department_id:
        filters |= Q(departments=profile.department_id)
    return qs.filter(filters).distinct()


def pending_claim_steps_for_user(user):
    """Bước hàng đợi phòng ban chờ user tiếp nhận."""
    from hrm.permissions import can_claim_cross_dept_step

    profile = get_profile(user)
    candidates = WorkTask.objects.filter(
        project__project_type=InternalProject.TYPE_CROSS_DEPT,
        project__status=InternalProject.STATUS_ACTIVE,
        assignee_mode=WorkTask.ASSIGNEE_DEPT_QUEUE,
        assignee__isnull=True,
        status=WorkTask.STATUS_PENDING_CLAIM,
    )
    if is_director(user):
        pass
    elif profile and profile.department_id:
        candidates = candidates.filter(target_department_id=profile.department_id)
    else:
        return WorkTask.objects.none()

    candidates = candidates.select_related(
        'project', 'target_department', 'depends_on',
    ).order_by('due_date', 'step_order', 'created_at')

    return candidates.filter(
        pk__in=[step.pk for step in candidates if can_claim_cross_dept_step(user, step)],
    )


def pending_claim_count_for_user(user):
    return pending_claim_steps_for_user(user).count()
