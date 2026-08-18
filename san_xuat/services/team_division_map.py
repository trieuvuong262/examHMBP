"""Map thủ công Bộ phận HR ↔ Tổ chuyền (Công việc tổ) + lọc NV phân công."""

from __future__ import annotations

import unicodedata

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from hrm.models import Division, ProfileConcurrentPosition
from san_xuat.hub_models import SxTeamDivisionMap
from san_xuat.services.progress_template import TEAM_SLUGS

User = get_user_model()

# team_slug → khóa tên bộ phận HR (đã fold), giống capacity_from_hrm._IE_WC_TO_HR_KEYS
_SLUG_HR_KEYS: dict[str, tuple[str, ...]] = {
    'cat': ('cat', 'trai', 'trai vai'),
    'inep': ('in ep', 'in ', 'ep logo', 'ep '),
    'theu': ('theu',),
    'may': ('may',),
    'ht': ('ui', 'gap', 'gap xep'),
    'gh': ('giao hang', 'thanh pham', 'tp'),
}

VALID_TEAM_SLUGS = frozenset(item[0] for item in TEAM_SLUGS)


def _fold(text: str) -> str:
    raw = unicodedata.normalize('NFD', (text or '').lower())
    raw = ''.join(ch for ch in raw if unicodedata.category(ch) != 'Mn')
    return raw.replace('đ', 'd').strip()


def team_slug_choices() -> list[tuple[str, str]]:
    return [(slug, label) for slug, _gk, _mk, label in TEAM_SLUGS]


def mapped_division_ids(slug: str) -> set[int]:
    s = (slug or '').strip().lower()
    if s not in VALID_TEAM_SLUGS:
        return set()
    return set(
        SxTeamDivisionMap.objects.filter(
            team_slug=s,
            is_active=True,
            is_demo=False,
        ).values_list('division_id', flat=True),
    )


def has_mapped_divisions(slug: str) -> bool:
    return bool(mapped_division_ids(slug))


def users_in_mapped_divisions(slug: str):
    """NV đang làm việc thuộc bộ phận đã map (primary hoặc kiêm nhiệm)."""
    div_ids = mapped_division_ids(slug)
    if not div_ids:
        return User.objects.none()

    concurrent_user_ids = set(
        ProfileConcurrentPosition.objects.filter(
            is_active=True,
            division_id__in=div_ids,
            profile__is_employed=True,
            profile__user__is_active=True,
        ).values_list('profile__user_id', flat=True),
    )
    return (
        User.objects.filter(is_active=True, profile__is_employed=True)
        .filter(
            Q(profile__division_id__in=div_ids)
            | Q(pk__in=concurrent_user_ids),
        )
        .select_related('profile')
        .distinct()
        .order_by('profile__full_name', 'username')
    )


def _assigner_sees_full_pool(assigner) -> bool:
    """GD / TP / TBP / superuser / thiết lập SX → thấy cả pool bộ phận đã map."""
    if not getattr(assigner, 'is_authenticated', False):
        return False
    if getattr(assigner, 'is_superuser', False):
        return True

    from hrm.concurrent_positions import effective_roles
    from hrm.menu_permissions import user_can_update_menu
    from hrm.module_permissions import MODULE_SAN_XUAT
    from hrm.permissions import (
        ROLE_DEPARTMENT_HEAD,
        ROLE_DIRECTOR,
        ROLE_DIVISION_HEAD,
    )

    roles = effective_roles(assigner)
    if roles & {ROLE_DIRECTOR, ROLE_DEPARTMENT_HEAD, ROLE_DIVISION_HEAD}:
        return True
    # Tổ trưởng (kể cả có update menu team_work_*) vẫn chỉ thấy cấp dưới.
    if user_can_update_menu(assigner, MODULE_SAN_XUAT, 'general_settings'):
        return True
    return False


def _user_option_label(user) -> str:
    """Nhãn dropdown phân công — chỉ hiện họ tên."""
    p = getattr(user, 'profile', None)
    name = ((getattr(p, 'full_name', None) or '') if p else '').strip()
    return name or user.get_full_name() or user.username


def assignee_candidate_ids_for_team(slug: str, assigner) -> set[int]:
    """Tập user pk được phép gán trên tổ `slug`."""
    pool = users_in_mapped_divisions(slug)
    if not pool.exists():
        return set()

    if _assigner_sees_full_pool(assigner):
        return set(pool.values_list('pk', flat=True))

    from hrm.concurrent_positions import get_manual_subordinate_users

    sub_ids = set(get_manual_subordinate_users(assigner).values_list('pk', flat=True))
    if not sub_ids:
        return set()
    return set(pool.filter(pk__in=sub_ids).values_list('pk', flat=True))


def assignee_candidates_for_team(slug: str, assigner, *, limit: int = 300) -> list[dict]:
    """Options dropdown phân công: [{id, label}, ...]."""
    ids = assignee_candidate_ids_for_team(slug, assigner)
    if not ids:
        return []
    qs = (
        User.objects.filter(pk__in=ids, is_active=True)
        .select_related('profile')
        .order_by('profile__full_name', 'username')[:limit]
    )
    return [{'id': u.pk, 'label': _user_option_label(u)} for u in qs]


def suggest_maps_from_names() -> dict[str, list[int]]:
    """Gợi ý map theo tên bộ phận phòng SẢN XUẤT — không ghi DB."""
    from san_xuat.services.capacity_from_hrm import _sx_department

    dept = _sx_department()
    result: dict[str, list[int]] = {slug: [] for slug in VALID_TEAM_SLUGS}
    if not dept:
        return result

    divisions = list(
        Division.objects.filter(department=dept, is_active=True).order_by('sort_order', 'name'),
    )
    claimed: set[int] = set()

    # Ưu tiên khóa dài hơn / cụ thể hơn để tránh MAY nuốt mọi thứ
    ordered_slugs = ('cat', 'inep', 'theu', 'ht', 'gh', 'may')
    for slug in ordered_slugs:
        keys = _SLUG_HR_KEYS.get(slug) or ()
        hits: list[tuple[int, int]] = []
        for div in divisions:
            if div.pk in claimed:
                continue
            folded = _fold(div.name)
            score = None
            for key in keys:
                if key == folded or folded.startswith(key + ' ') or folded.startswith(key + '('):
                    score = 0
                    break
                if key in folded:
                    score = len(folded)
                    break
            if score is not None:
                hits.append((score, div.pk))
        hits.sort(key=lambda x: (x[0], x[1]))
        for _score, div_id in hits:
            if div_id in claimed:
                continue
            result[slug].append(div_id)
            claimed.add(div_id)
    return result


def current_maps_by_slug() -> dict[str, list[int]]:
    out: dict[str, list[int]] = {slug: [] for slug in VALID_TEAM_SLUGS}
    rows = (
        SxTeamDivisionMap.objects.filter(is_demo=False, is_active=True)
        .order_by('team_slug', 'division__sort_order', 'division_id')
        .values_list('team_slug', 'division_id')
    )
    for slug, div_id in rows:
        if slug in out:
            out[slug].append(div_id)
    return out


def sx_production_divisions():
    """Bộ phận active thuộc phòng SẢN XUẤT (để chọn trên UI)."""
    from san_xuat.services.capacity_from_hrm import _sx_department

    dept = _sx_department()
    if not dept:
        return Division.objects.filter(is_active=True).order_by('sort_order', 'name')
    return Division.objects.filter(
        department=dept,
        is_active=True,
    ).order_by('sort_order', 'name')


@transaction.atomic
def save_team_maps(
    payload: dict[str, list[int]],
    *,
    saved_by=None,
) -> dict[str, int]:
    """Lưu map từ form: {slug: [division_id, ...]}.

    Mỗi bộ phận chỉ thuộc một tổ — nếu trùng trong payload, slug sau ghi đè.
    """
    cleaned: dict[int, str] = {}
    for slug, raw_ids in (payload or {}).items():
        s = (slug or '').strip().lower()
        if s not in VALID_TEAM_SLUGS:
            continue
        for raw in raw_ids or []:
            try:
                div_id = int(raw)
            except (TypeError, ValueError):
                continue
            if div_id > 0:
                cleaned[div_id] = s

    valid_div_ids = set(
        Division.objects.filter(pk__in=cleaned.keys(), is_active=True).values_list('pk', flat=True),
    )
    cleaned = {div_id: slug for div_id, slug in cleaned.items() if div_id in valid_div_ids}

    existing = {
        row.division_id: row
        for row in SxTeamDivisionMap.objects.filter(is_demo=False).select_for_update()
    }

    kept: set[int] = set()
    created = updated = deactivated = 0
    actor = saved_by if getattr(saved_by, 'is_authenticated', False) else None

    for div_id, slug in cleaned.items():
        row = existing.get(div_id)
        if row is None:
            SxTeamDivisionMap.objects.create(
                team_slug=slug,
                division_id=div_id,
                is_active=True,
                is_demo=False,
                created_by=actor,
            )
            created += 1
        else:
            fields: list[str] = []
            if row.team_slug != slug:
                row.team_slug = slug
                fields.append('team_slug')
            if not row.is_active:
                row.is_active = True
                fields.append('is_active')
            if fields:
                row.save(update_fields=fields)
                updated += 1
            kept.add(div_id)

        kept.add(div_id)

    for div_id, row in existing.items():
        if div_id not in kept and row.is_active:
            row.is_active = False
            row.save(update_fields=['is_active'])
            deactivated += 1

    return {'created': created, 'updated': updated, 'deactivated': deactivated}
