"""Map thủ công Bộ phận HR ↔ Tổ chuyền (Công việc tổ) + lọc NV phân công."""

from __future__ import annotations

import re
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
_DIV_SLUG_RE = re.compile(r'^d(\d+)$')
TEAM_MENU_ICONS = {
    'cat': 'bi-scissors',
    'inep': 'bi-printer',
    'theu': 'bi-flower1',
    'may': 'bi-grid-3x3-gap',
    'ht': 'bi-layers',
    'gh': 'bi-truck',
}


def _fold(text: str) -> str:
    raw = unicodedata.normalize('NFD', (text or '').lower())
    raw = ''.join(ch for ch in raw if unicodedata.category(ch) != 'Mn')
    return raw.replace('đ', 'd').strip()


def team_slug_choices() -> list[tuple[str, str]]:
    return [(slug, label) for slug, _gk, _mk, label in TEAM_SLUGS]


def division_id_from_team_slug(slug: str) -> int | None:
    m = _DIV_SLUG_RE.match((slug or '').strip().lower())
    if not m:
        return None
    return int(m.group(1))


def team_slug_for_division_id(division_id: int) -> str:
    return f'd{int(division_id)}'


def _stage_slug_for_division(div, *, mapped: dict[int, str] | None = None) -> str:
    did = int(getattr(div, 'pk', 0) or 0)
    if mapped is not None:
        if did in mapped:
            return mapped[did]
        from san_xuat.services.capacity_from_hrm import _fold, _team_slug_from_folded

        return _team_slug_from_folded(_fold(getattr(div, 'name', '') or '')) or ''
    hit = (
        SxTeamDivisionMap.objects.filter(
            division_id=did,
            is_active=True,
            is_demo=False,
        )
        .values_list('team_slug', flat=True)
        .first()
    )
    if hit:
        return (hit or '').strip().lower()
    from san_xuat.services.capacity_from_hrm import _fold, _team_slug_from_folded

    return _team_slug_from_folded(_fold(getattr(div, 'name', '') or '')) or ''


def team_from_hr_division_slug(slug: str) -> dict | None:
    """Tổ menu = bộ phận HR phòng SẢN XUẤT / ĐBCL (`d{id}`)."""
    did = division_id_from_team_slug(slug)
    if not did:
        return None
    from san_xuat.services.capacity_from_hrm import (
        hr_divisions_for_ie_groups,
        work_center_code_for_division,
    )

    div = hr_divisions_for_ie_groups().filter(pk=did).first()
    if not div:
        return None
    stage = _stage_slug_for_division(div)
    group_key = menu_key = ''
    for item_slug, gk, mk, _label in TEAM_SLUGS:
        if item_slug == stage:
            group_key, menu_key = gk, mk
            break
    return {
        'slug': team_slug_for_division_id(div.pk),
        'division_id': int(div.pk),
        'group_key': group_key,
        'menu_key': menu_key or 'team_work',
        'label': (div.name or '').strip() or f'Bộ phận {div.pk}',
        'group_label': (
            (div.department.name if getattr(div, 'department_id', None) else '') or ''
        ).strip(),
        'work_center_code': work_center_code_for_division(div.pk),
        'stage_slug': stage,
    }


def team_work_menu_items(user) -> list[dict]:
    """Menu tổ: mỗi bộ phận HR thuộc SẢN XUẤT + ĐẢM BẢO CHẤT LƯỢNG."""
    from hrm.menu_permissions import user_can_access_menu
    from hrm.module_permissions import MODULE_SAN_XUAT
    from san_xuat.services.capacity_from_hrm import (
        _fold,
        hr_divisions_for_ie_groups,
        work_center_code_for_division,
    )

    can_all = user_can_access_menu(user, MODULE_SAN_XUAT, 'team_work')
    allowed_keys = {'team_work'} if can_all else set()
    for _slug, _gk, menu_key, _label in TEAM_SLUGS:
        if can_all or user_can_access_menu(user, MODULE_SAN_XUAT, menu_key):
            allowed_keys.add(menu_key)

    mapped: dict[int, str] = {}
    for stage, ids in current_maps_by_slug().items():
        for did in ids:
            mapped[int(did)] = stage

    items: list[dict] = []
    for div in hr_divisions_for_ie_groups():
        stage = _stage_slug_for_division(div, mapped=mapped)
        menu_key = 'team_work'
        for item_slug, _gk, mk, _label in TEAM_SLUGS:
            if item_slug == stage:
                menu_key = mk
                break
        if menu_key not in allowed_keys and 'team_work' not in allowed_keys:
            continue
        folded = _fold(div.name or '')
        icon = TEAM_MENU_ICONS.get(stage) or (
            'bi-clipboard-check' if 'qc' in folded or 'chat luong' in folded else 'bi-people'
        )
        items.append({
            'slug': team_slug_for_division_id(div.pk),
            'label': (div.name or '').strip() or f'Bộ phận {div.pk}',
            'icon': icon,
            'menu_key': menu_key,
            'division_id': int(div.pk),
            'work_center_code': work_center_code_for_division(div.pk),
        })
    if items:
        return items
    for slug, _gk, menu_key, label in TEAM_SLUGS:
        if menu_key not in allowed_keys and 'team_work' not in allowed_keys:
            continue
        items.append({
            'slug': slug,
            'label': f'Tổ {label}' if not label.lower().startswith('tổ') else label,
            'icon': TEAM_MENU_ICONS.get(slug, 'bi-people'),
            'menu_key': menu_key,
            'division_id': 0,
            'work_center_code': '',
        })
    return items


def khsx_slug_for_team(team: dict | None, slug: str = '') -> str:
    """Slug KHSX (cat/may/ht…) tương ứng tổ menu HR `d{id}`."""
    if team:
        stage = (team.get('stage_slug') or '').strip().lower()
        if stage:
            return stage
        s = (team.get('slug') or '').strip().lower()
        if s and not division_id_from_team_slug(s):
            return s
    raw = (slug or '').strip().lower()
    team = team or team_from_hr_division_slug(raw)
    if team:
        stage = (team.get('stage_slug') or '').strip().lower()
        if stage:
            return stage
    return raw


def team_slug_aliases(slug: str, team: dict | None = None) -> list[str]:
    """`d25` ↔ `may` — dùng khi đọc KHSX / QC / GC."""
    raw = (slug or '').strip().lower()
    meta = team or (team_from_hr_division_slug(raw) if division_id_from_team_slug(raw) else None)
    out: list[str] = []
    if raw:
        out.append(raw)
    stage = khsx_slug_for_team(meta, raw)
    if stage and stage not in out:
        out.append(stage)
    return out


def board_slug_from_work_center_id(work_center_id: int) -> str:
    """Slug menu phân công từ tổ năng lực KHSX (HRD-{division})."""
    wid = int(work_center_id or 0)
    if wid <= 0:
        return ''
    from san_xuat.hub_models import SxWorkCenter
    from san_xuat.services.capacity_from_hrm import division_id_from_work_center_code

    wc = SxWorkCenter.objects.filter(pk=wid).only('id', 'code', 'division_id').first()
    if wc is None:
        return ''
    did = int(getattr(wc, 'division_id', 0) or 0) or (
        division_id_from_work_center_code(wc.code) or 0
    )
    if did <= 0:
        return ''
    meta = team_from_hr_division_slug(team_slug_for_division_id(did))
    return (meta or {}).get('slug') or ''


def mapped_division_ids(slug: str) -> set[int]:
    s = (slug or '').strip().lower()
    did = division_id_from_team_slug(s)
    if did:
        from san_xuat.services.capacity_from_hrm import hr_divisions_for_ie_groups

        if hr_divisions_for_ie_groups().filter(pk=did).exists():
            return {did}
        return set()
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
    """Bộ phận active thuộc phòng SẢN XUẤT và ĐẢM BẢO CHẤT LƯỢNG."""
    from san_xuat.services.capacity_from_hrm import hr_divisions_for_ie_groups

    qs = hr_divisions_for_ie_groups()
    if qs.exists():
        return qs
    return Division.objects.filter(is_active=True).order_by('sort_order', 'name')


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
