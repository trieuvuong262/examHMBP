"""Quyền theo nghiệp vụ Tuyển dụng.

Hai lớp kiểm tra:

1. **Quyền chức năng** — menu Tuyển dụng (``candidates`` / ``jobs``) trong ma trận nhóm quyền.
2. **Phạm vi dữ liệu** — chỉ thấy vị trí (và ứng viên của vị trí) mình phụ trách:
   * Trưởng bộ phận → vị trí gắn bộ phận mình làm trưởng.
   * Trưởng phòng → mọi vị trí của phòng mình làm trưởng.
   * Giám đốc → phòng ban được gán (vị trí chính + kiêm nhiệm); không gán phòng = toàn công ty.
   * Nhóm quyền có quyền bổ sung «Tuyển dụng — xem ứng viên mọi phòng ban» (HCNS, TGĐ) → tất cả.
   * superuser / admin hệ thống → tất cả.

Đánh giá hồ sơ chỉ theo phạm vi **quản lý** (mục 2, không gồm quyền bổ sung):
HR thấy hết nhưng không đánh giá thay quản lý phòng ban khác.
Người được giao phỏng vấn luôn xem được hồ sơ + CV của ứng viên đó.
"""

from dataclasses import dataclass, field

from django.db.models import Q

from hrm.concurrent_positions import (
    _is_department_head_slot,
    _is_division_head_slot,
    get_active_concurrent_positions,
    user_is_division_head,
)
from hrm.group_permissions import get_user_group_permissions
from hrm.menu_permissions import user_can_menu_action
from hrm.module_permissions import MODULE_HRM, MODULE_RECRUITMENT, bypass_department_modules
from hrm.permissions import ROLE_DIRECTOR, get_profile

MENU_CANDIDATES = 'candidates'
MENU_JOBS = 'jobs'
MENU_SETTINGS = 'settings'
EXTRA_ALL_DEPARTMENTS = 'all_departments'
EXTRA_FINAL_APPROVE = 'final_approve'


def can_candidates(user, action: str = 'view') -> bool:
    return user_can_menu_action(user, MODULE_RECRUITMENT, MENU_CANDIDATES, action)


def can_jobs(user, action: str = 'view') -> bool:
    return user_can_menu_action(user, MODULE_RECRUITMENT, MENU_JOBS, action)


def can_settings(user, action: str = 'view') -> bool:
    return user_can_menu_action(user, MODULE_RECRUITMENT, MENU_SETTINGS, action)


def can_onboard(user) -> bool:
    """Tạo tài khoản nhân viên = quyền Tuyển dụng + quyền thêm NV bên HRM."""
    return can_candidates(user, 'update') and user_can_menu_action(user, MODULE_HRM, 'users', 'create')


def is_hiring_manager(user) -> bool:
    """Trưởng bộ phận, Trưởng phòng hoặc Giám đốc (kể cả kiêm nhiệm)."""
    return bool(getattr(user, 'is_authenticated', False)) and user_is_division_head(user)


def can_final_approve(user) -> bool:
    """Giám đốc duyệt cấp 2 (mọi phòng ban) — quyền bổ sung trong nhóm quyền hoặc superuser."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if bypass_department_modules(user):
        return True
    extras = get_user_group_permissions(user).get(MODULE_RECRUITMENT, {}).get('extras')
    return bool(isinstance(extras, dict) and extras.get(EXTRA_FINAL_APPROVE))


def final_queue(user):
    """Hồ sơ phỏng vấn Đạt đang chờ giám đốc duyệt — rỗng nếu user không có quyền duyệt."""
    from recruitment.models import Candidate, Interview

    if not can_final_approve(user):
        return Candidate.objects.none()
    return Candidate.objects.filter(
        status=Candidate.STATUS_INTERVIEWING,
        interview__result=Interview.RESULT_PASS,
        interview__final_result=Interview.FINAL_PENDING,
    )


# ---------------------------------------------------------------- phạm vi

@dataclass
class Scope:
    all: bool = False
    department_ids: set = field(default_factory=set)
    division_ids: set = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not (self.all or self.department_ids or self.division_ids)

    def job_q(self, prefix: str = '') -> Q:
        if self.all:
            return Q()
        if self.empty:
            return Q(**{f'{prefix}pk__in': []})
        return (
            Q(**{f'{prefix}target_department_id__in': self.department_ids})
            | Q(**{f'{prefix}target_division_id__in': self.division_ids})
        )

    def contains(self, job) -> bool:
        if self.all:
            return True
        if job.target_department_id and job.target_department_id in self.department_ids:
            return True
        return bool(job.target_division_id and job.target_division_id in self.division_ids)


def managed_scope(user) -> Scope:
    """Phạm vi quản lý theo vị trí chính + kiêm nhiệm (không tính quyền bổ sung HR)."""
    if not getattr(user, 'is_authenticated', False):
        return Scope()
    if bypass_department_modules(user):
        return Scope(all=True)

    from hrm.request_cache import get_or_set, user_key

    return get_or_set(user_key('rc_managed_scope', user), lambda: _compute_managed_scope(user))


def _compute_managed_scope(user) -> Scope:
    profile = get_profile(user)
    if not profile:
        return Scope()
    scope = Scope()
    slots = [(profile, None)] + [(profile, cp) for cp in get_active_concurrent_positions(profile)]
    for prof, cp in slots:
        role = cp.role if cp else prof.role
        dept_id = cp.department_id if cp else prof.department_id
        div_id = cp.division_id if cp else prof.division_id
        if role == ROLE_DIRECTOR and not dept_id and not div_id:
            scope.all = True  # Giám đốc không gắn phòng ban — phụ trách toàn công ty
        elif _is_department_head_slot(prof, cp):
            scope.department_ids.add(dept_id)
        elif _is_division_head_slot(prof, cp):
            scope.division_ids.add(div_id)
    return scope


def has_all_departments(user) -> bool:
    """Quyền bổ sung trong nhóm quyền — HR / TGĐ xem ứng viên mọi phòng ban."""
    if bypass_department_modules(user):
        return True
    extras = get_user_group_permissions(user).get(MODULE_RECRUITMENT, {}).get('extras')
    return bool(isinstance(extras, dict) and extras.get(EXTRA_ALL_DEPARTMENTS))


def visible_scope(user) -> Scope:
    """Phạm vi dữ liệu trên các màn hình Tuyển dụng."""
    if has_all_departments(user):
        return Scope(all=True)
    return managed_scope(user)


def visible_jobs_q(user, prefix: str = '') -> Q:
    return visible_scope(user).job_q(prefix)


def manager_job_filter(user) -> Q:
    """Vị trí quản lý được đánh giá / đề xuất ứng viên."""
    return managed_scope(user).job_q()


def can_access_job(user, job) -> bool:
    return visible_scope(user).contains(job)


def manager_can_access_job(user, job) -> bool:
    return is_hiring_manager(user) and managed_scope(user).contains(job)


def is_interviewer(user, candidate) -> bool:
    interview = candidate.interview_or_none
    return bool(interview and interview.interviewers.filter(pk=user.pk).exists())


def can_view_candidate(user, candidate) -> bool:
    """Xem hồ sơ + CV: HR/quản lý trong phạm vi, hoặc người được giao phỏng vấn."""
    if not getattr(user, 'is_authenticated', False):
        return False
    job = candidate.job_posting
    return (
        (can_candidates(user, 'view') and can_access_job(user, job))
        or manager_can_access_job(user, job)
        or is_interviewer(user, candidate)
    )


def can_record_interview_result(user, candidate) -> bool:
    """Nhập kết quả PV: người được giao phỏng vấn, quản lý phụ trách vị trí, hoặc HR có quyền Sửa."""
    from recruitment.models import Candidate, Interview

    if not getattr(user, 'is_authenticated', False) or candidate.status != Candidate.STATUS_INTERVIEWING:
        return False
    interview = candidate.interview_or_none
    if not interview or interview.result != Interview.RESULT_PENDING:
        return False
    return (
        is_interviewer(user, candidate)
        or manager_can_access_job(user, candidate.job_posting)
        or (can_candidates(user, 'update') and can_access_job(user, candidate.job_posting))
    )


def interview_queue(user):
    """Ứng viên đang chờ kết quả PV mà user là người phỏng vấn hoặc quản lý phụ trách vị trí."""
    from recruitment.models import Candidate, Interview, JobPosting

    if not getattr(user, 'is_authenticated', False):
        return Candidate.objects.none()
    q = Q(interview__interviewers=user)
    if is_hiring_manager(user):
        q |= Q(job_posting__in=JobPosting.objects.filter(manager_job_filter(user)))
    ids = Candidate.objects.filter(
        q, status=Candidate.STATUS_INTERVIEWING, interview__result=Interview.RESULT_PENDING,
    ).values('pk')
    return Candidate.objects.filter(pk__in=ids)


def can_review_candidate(user, candidate) -> bool:
    from recruitment.models import Candidate

    return (
        candidate.status == Candidate.STATUS_REVIEWING
        and manager_can_access_job(user, candidate.job_posting)
    )


def scope_label(user, *, managed: bool = False) -> str:
    """Mô tả ngắn phạm vi — hiện dưới tiêu đề trang."""
    from hrm.models import Department, Division

    scope = managed_scope(user) if managed else visible_scope(user)
    if scope.all:
        return 'Tất cả phòng ban'
    names = list(
        Department.objects.filter(pk__in=scope.department_ids).order_by('sort_order', 'name')
        .values_list('name', flat=True)
    )
    names += [
        f'{d.department.name} · {d.name}' if d.department_id else d.name
        for d in Division.objects.filter(pk__in=scope.division_ids).select_related('department')
    ]
    return ', '.join(names) or 'Chưa được giao phòng ban / bộ phận'
