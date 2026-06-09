"""
Vị trí kiêm nhiệm — gộp quyền tổ chức với vị trí chính trên Profile.

Module CRUD (permission_group) vẫn theo vị trí chính; kiêm nhiệm mở phạm vi
phòng/bộ phận/vai trò cho báo cáo, công việc, KPI, yêu cầu, sơ đồ tổ chức.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Q

from hrm.permissions import (
    MANAGER_ROLES,
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
    get_profile,
    user_role,
)

MANAGER_SLOT_ROLES = {ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD}
from hrm.user_search import exclude_hidden_hrm_profiles, visible_employed_profiles

_HEAD_POSITION_NAMES = ('Trưởng phòng', 'Trưởng Phòng', 'TRUONG PHONG')
_DIVISION_HEAD_POSITION_NAMES = ('Trưởng bộ phận', 'Trưởng Bộ Phận', 'TRUONG BO PHAN')


def get_active_concurrent_positions(profile):
    if profile is None:
        return []
    if hasattr(profile, '_prefetched_objects_cache') and 'concurrent_positions' in profile._prefetched_objects_cache:
        return [cp for cp in profile.concurrent_positions.all() if cp.is_active]
    return list(
        profile.concurrent_positions.filter(is_active=True).select_related(
            'department', 'division',
        ).order_by('sort_order', 'id'),
    )


def prefetch_concurrent_positions(queryset):
    from hrm.models import ProfileConcurrentPosition

    return queryset.prefetch_related(
        'concurrent_positions',
    )


def effective_roles(user) -> set[str]:
    if not getattr(user, 'is_authenticated', False):
        return {ROLE_EMPLOYEE}
    roles = {ROLE_DIRECTOR} if user.is_superuser else {user_role(user)}
    profile = get_profile(user)
    if profile:
        for cp in get_active_concurrent_positions(profile):
            roles.add(cp.role)
    return roles


def user_has_role(user, role: str) -> bool:
    return role in effective_roles(user)


def user_is_director(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    return user.is_superuser or ROLE_DIRECTOR in effective_roles(user)


def user_is_team_leader(user) -> bool:
    return ROLE_TEAM_LEADER in effective_roles(user)


def user_is_department_head(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    roles = effective_roles(user)
    return ROLE_DEPARTMENT_HEAD in roles or ROLE_DIRECTOR in roles or user.is_superuser


def user_is_division_head(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    roles = effective_roles(user)
    return (
        ROLE_DIVISION_HEAD in roles
        or ROLE_DEPARTMENT_HEAD in roles
        or ROLE_DIRECTOR in roles
        or user.is_superuser
    )


def user_is_manager(user) -> bool:
    return bool(effective_roles(user) & MANAGER_ROLES) or user_is_director(user)


def _slot_department_id(profile, concurrent=None) -> int | None:
    if concurrent is not None:
        return concurrent.department_id
    return profile.department_id if profile else None


def _slot_division_id(profile, concurrent=None) -> int | None:
    if concurrent is not None:
        return concurrent.division_id
    return profile.division_id if profile else None


def effective_department_ids(user) -> set[int]:
    profile = get_profile(user)
    if not profile:
        return set()
    ids = set()
    if profile.department_id:
        ids.add(profile.department_id)
    for cp in get_active_concurrent_positions(profile):
        if cp.department_id:
            ids.add(cp.department_id)
    return ids


def effective_division_ids(user) -> set[int]:
    profile = get_profile(user)
    if not profile:
        return set()
    ids = set()
    if profile.division_id:
        ids.add(profile.division_id)
    for cp in get_active_concurrent_positions(profile):
        if cp.division_id:
            ids.add(cp.division_id)
    return ids


def _normalize_position(name: str) -> str:
    return (name or '').strip()


def profile_matches_org_slot(
    profile,
    *,
    department_id: int | None,
    division_id: int | None,
    job_position: str,
) -> bool:
    """Primary hoặc concurrent khớp ô sơ đồ."""
    pos = _normalize_position(job_position)
    if not pos:
        return False

    def _match(dept_id, div_id, position_name):
        if _normalize_position(position_name) != pos:
            return False
        if division_id is not None and div_id != division_id:
            return False
        if department_id is not None and dept_id != department_id:
            return False
        return True

    if _match(profile.department_id, profile.division_id, profile.job_position):
        return True
    for cp in get_active_concurrent_positions(profile):
        if _match(cp.department_id, cp.division_id, cp.job_position):
            return True
    return False


def _is_department_head_slot(profile, concurrent=None) -> bool:
    role = concurrent.role if concurrent else profile.role
    dept_id = _slot_department_id(profile, concurrent)
    div_id = _slot_division_id(profile, concurrent)
    job_pos = concurrent.job_position if concurrent else profile.job_position
    if not dept_id or div_id:
        return False
    if job_pos in _HEAD_POSITION_NAMES:
        return True
    return role in {ROLE_DEPARTMENT_HEAD, ROLE_DIVISION_HEAD, ROLE_DIRECTOR}


def _is_division_head_slot(profile, concurrent=None) -> bool:
    role = concurrent.role if concurrent else profile.role
    div_id = _slot_division_id(profile, concurrent)
    job_pos = concurrent.job_position if concurrent else profile.job_position
    if not div_id:
        return False
    if role in {ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR}:
        return True
    return job_pos in _DIVISION_HEAD_POSITION_NAMES


def heads_for_department(department_id: int):
    """Profile queryset — trưởng phòng (primary + kiêm nhiệm)."""
    from hrm.models import Profile, ProfileConcurrentPosition

    primary_ids = set(
        exclude_hidden_hrm_profiles(
            Profile.objects.filter(
                is_employed=True,
                department_id=department_id,
                division__isnull=True,
            ).filter(
                Q(job_position__in=_HEAD_POSITION_NAMES)
                | Q(role=ROLE_DEPARTMENT_HEAD),
            ),
        ).values_list('pk', flat=True),
    )
    concurrent_ids = ProfileConcurrentPosition.objects.filter(
        is_active=True,
        department_id=department_id,
        division__isnull=True,
        profile__is_employed=True,
    ).filter(
        Q(job_position__in=_HEAD_POSITION_NAMES)
        | Q(role=ROLE_DEPARTMENT_HEAD),
    ).values_list('profile_id', flat=True)
    all_ids = primary_ids | set(concurrent_ids)
    return exclude_hidden_hrm_profiles(
        Profile.objects.filter(pk__in=all_ids, is_employed=True),
    ).select_related('user').order_by('employee_code', 'full_name')


def heads_for_division(department_id: int | None, division_id: int):
    """Profile queryset — trưởng bộ phận (primary + kiêm nhiệm)."""
    from hrm.models import Profile, ProfileConcurrentPosition

    primary_qs = exclude_hidden_hrm_profiles(
        Profile.objects.filter(
            is_employed=True,
            division_id=division_id,
        ).filter(
            Q(role__in={ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR})
            | Q(job_position__in=_DIVISION_HEAD_POSITION_NAMES),
        ),
    )
    if department_id:
        primary_qs = primary_qs.filter(department_id=department_id)
    primary_ids = set(primary_qs.values_list('pk', flat=True))

    concurrent_qs = ProfileConcurrentPosition.objects.filter(
        is_active=True,
        division_id=division_id,
        profile__is_employed=True,
    ).filter(
        Q(role__in={ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR})
        | Q(job_position__in=_DIVISION_HEAD_POSITION_NAMES),
    )
    if department_id:
        concurrent_qs = concurrent_qs.filter(department_id=department_id)
    concurrent_ids = set(concurrent_qs.values_list('profile_id', flat=True))

    all_ids = primary_ids | concurrent_ids
    qs = exclude_hidden_hrm_profiles(
        Profile.objects.filter(pk__in=all_ids, is_employed=True),
    ).select_related('user').order_by('employee_code', 'full_name')
    return qs


def profiles_at_org_position(
    department_id: int | None,
    division_id: int,
    position_name: str,
):
    """NV tại vị trí — primary khớp HOẶC concurrent khớp (có thể trùng user)."""
    from hrm.models import Profile, ProfileConcurrentPosition

    pos = _normalize_position(position_name)
    primary_qs = exclude_hidden_hrm_profiles(
        Profile.objects.filter(
            is_employed=True,
            division_id=division_id,
            job_position__iexact=pos,
        ),
    ).select_related('user')
    if department_id:
        primary_qs = primary_qs.filter(department_id=department_id)

    concurrent_profile_ids = ProfileConcurrentPosition.objects.filter(
        is_active=True,
        division_id=division_id,
        job_position__iexact=pos,
        profile__is_employed=True,
    )
    if department_id:
        concurrent_profile_ids = concurrent_profile_ids.filter(department_id=department_id)
    concurrent_ids = set(concurrent_profile_ids.values_list('profile_id', flat=True))

    primary_ids = set(primary_qs.values_list('pk', flat=True))
    all_ids = primary_ids | concurrent_ids
    return exclude_hidden_hrm_profiles(
        Profile.objects.filter(pk__in=all_ids, is_employed=True),
    ).select_related('user').order_by('employee_code', 'full_name')


def concurrent_position_user_ids_at_slot(
    department_id: int | None,
    division_id: int,
    position_name: str,
) -> set[int]:
    """User IDs chỉ từ kiêm nhiệm (để đánh dấu badge trên sơ đồ)."""
    from hrm.models import ProfileConcurrentPosition

    pos = _normalize_position(position_name)
    qs = ProfileConcurrentPosition.objects.filter(
        is_active=True,
        division_id=division_id,
        job_position__iexact=pos,
        profile__is_employed=True,
    )
    if department_id:
        qs = qs.filter(department_id=department_id)
    from hrm.models import Profile

    return set(
        Profile.objects.filter(
            pk__in=qs.values_list('profile_id', flat=True),
        ).values_list('user_id', flat=True),
    )


def auto_managed_user_ids(user) -> set[int]:
    """NV trong phạm vi auto theo slot kiêm nhiệm + primary manager role."""
    profile = get_profile(user)
    if not profile or not profile.is_employed:
        return set()

    ids: set[int] = set()
    if user_is_director(user):
        return set(
            User.objects.filter(
                profile__is_employed=True,
                is_active=True,
            ).exclude(pk=user.pk).values_list('pk', flat=True),
        )

    slots: list[tuple[str, int | None, int | None]] = []
    slots.append((profile.role, profile.department_id, profile.division_id))
    for cp in get_active_concurrent_positions(profile):
        slots.append((cp.role, cp.department_id, cp.division_id))

    for role, dept_id, div_id in slots:
        if role == ROLE_TEAM_LEADER and div_id and dept_id:
            qs = visible_employed_profiles(division_id=div_id, department_id=dept_id)
            ids.update(qs.values_list('user_id', flat=True))
        elif role == ROLE_DIVISION_HEAD and div_id:
            qs = visible_employed_profiles(division_id=div_id, department_id=dept_id)
            ids.update(qs.values_list('user_id', flat=True))
        elif role == ROLE_DIVISION_HEAD and dept_id:
            qs = visible_employed_profiles(department_id=dept_id)
            ids.update(qs.values_list('user_id', flat=True))
        elif role == ROLE_DEPARTMENT_HEAD and dept_id:
            qs = visible_employed_profiles(department_id=dept_id)
            ids.update(qs.values_list('user_id', flat=True))

    ids.discard(user.pk)
    return ids


def _concurrent_slot_subordinate_ids(profile) -> set[int]:
    from hrm.models import ProfileConcurrentPosition

    ids: set[int] = set()
    active_slots = ProfileConcurrentPosition.objects.filter(
        profile=profile,
        is_active=True,
        role__in=MANAGER_SLOT_ROLES,
    ).prefetch_related('subordinates')
    for slot in active_slots:
        ids.update(
            slot.subordinates.filter(
                is_active=True,
                profile__is_employed=True,
            ).values_list('pk', flat=True),
        )
    return ids


def get_effective_subordinate_users(viewer):
    """Union M2M cấp dưới (chính + từng slot kiêm) + auto scope."""
    if not getattr(viewer, 'is_authenticated', False):
        return User.objects.none()

    profile = get_profile(viewer)
    if not profile:
        return User.objects.none()

    manual_ids = set(
        profile.subordinates.filter(
            is_active=True,
            profile__is_employed=True,
        ).values_list('pk', flat=True),
    )
    manual_ids |= _concurrent_slot_subordinate_ids(profile)
    auto_ids = auto_managed_user_ids(viewer)
    all_ids = manual_ids | auto_ids
    if not all_ids:
        return User.objects.none()

    return User.objects.filter(pk__in=all_ids).select_related('profile').order_by(
        'profile__full_name', 'username',
    )


def concurrent_positions_summary(profile) -> list[dict]:
    """Danh sách slot kiêm nhiệm cho UI."""
    rows = []
    for cp in get_active_concurrent_positions(profile):
        rows.append({
            'id': cp.pk,
            'department': cp.department.name if cp.department_id else '',
            'division': cp.division.name if cp.division_id else '',
            'job_position': cp.job_position,
            'job_title': cp.job_title,
            'role': cp.role,
            'role_display': cp.get_role_display(),
            'notes': cp.notes,
            'subordinate_count': cp.subordinates.filter(
                is_active=True,
                profile__is_employed=True,
            ).count(),
        })
    return rows


def role_display_extended(user) -> str:
    """Nhãn vai trò chính + số kiêm nhiệm."""
    profile = get_profile(user)
    if not profile:
        return 'Nhân viên'
    base = profile.get_role_display()
    count = len(get_active_concurrent_positions(profile))
    if count:
        return f'{base} (+{count} kiêm nhiệm)'
    return base


def department_has_division_heads_extended(department) -> bool:
    """Có trưởng bộ phận trong phòng (primary hoặc kiêm nhiệm)."""
    if not department:
        return False
    from hrm.models import Profile, ProfileConcurrentPosition

    if User.objects.filter(
        profile__department=department,
        profile__role=ROLE_DIVISION_HEAD,
        profile__is_employed=True,
        is_active=True,
    ).exists():
        return True
    return ProfileConcurrentPosition.objects.filter(
        is_active=True,
        department=department,
        role=ROLE_DIVISION_HEAD,
        profile__is_employed=True,
        profile__user__is_active=True,
    ).exists()


def department_has_department_heads_extended(department) -> bool:
    """Có trưởng phòng trong phòng (primary hoặc kiêm nhiệm)."""
    if not department:
        return False
    from hrm.models import Profile, ProfileConcurrentPosition

    if User.objects.filter(
        profile__department=department,
        profile__role=ROLE_DEPARTMENT_HEAD,
        profile__is_employed=True,
        is_active=True,
    ).exists():
        return True
    if Profile.objects.filter(
        is_employed=True,
        department_id=department.id,
        division__isnull=True,
        job_position__in=_HEAD_POSITION_NAMES,
    ).exists():
        return True
    return ProfileConcurrentPosition.objects.filter(
        is_active=True,
        department=department,
        role=ROLE_DEPARTMENT_HEAD,
        profile__is_employed=True,
        profile__user__is_active=True,
    ).exists()


def department_has_team_leaders_extended(department) -> bool:
    """Có tổ trưởng trong phòng (primary hoặc kiêm nhiệm)."""
    if not department:
        return False
    from hrm.models import Profile, ProfileConcurrentPosition

    if User.objects.filter(
        profile__department=department,
        profile__role=ROLE_TEAM_LEADER,
        profile__is_employed=True,
        is_active=True,
    ).exists():
        return True
    return ProfileConcurrentPosition.objects.filter(
        is_active=True,
        department=department,
        role=ROLE_TEAM_LEADER,
        profile__is_employed=True,
        profile__user__is_active=True,
    ).exists()


def find_manager_with_subordinate(user, role: str):
    """Tìm manager có user trong subordinates M2M hoặc auto scope."""
    if not user or not user.is_authenticated:
        return None
    profile = get_profile(user)
    if not profile or not profile.department_id:
        return None

    candidates = User.objects.filter(
        is_active=True,
        profile__is_employed=True,
    ).select_related('profile')

    for manager in candidates.order_by('profile__full_name', 'username'):
        if manager.pk == user.pk:
            continue
        if role not in effective_roles(manager):
            continue
        mgr_profile = get_profile(manager)
        if mgr_profile and mgr_profile.subordinates.filter(pk=user.pk).exists():
            return manager
        for cp in get_active_concurrent_positions(mgr_profile):
            if cp.role != role:
                continue
            if cp.subordinates.filter(pk=user.pk).exists():
                return manager
        if user.pk in auto_managed_user_ids(manager):
            return manager
    return None
