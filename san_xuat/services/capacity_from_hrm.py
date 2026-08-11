"""Đồng bộ Năng lực SX (SxWorkCenter) từ cơ cấu HR — bộ phận phòng SẢN XUẤT."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from hrm.models import Department, Division, Profile
from hrm.permissions import ROLE_DIVISION_HEAD, ROLE_TEAM_LEADER
from san_xuat.hub_models import SxTeamHrMap, SxWorkCenter

SX_DEPT_NAMES = ('SẢN XUẤT', 'SAN XUAT')
CODE_PREFIX = 'HRD-'
LEGACY_FAKE_CODES = frozenset({
    'TO-MAY-1', 'TO-MAY-2', 'TO-DG', 'TO-FULLCHECK', 'CHUYEN-01',
})
LEGACY_FAKE_TEAMS = frozenset({'Tổ May 1', 'Tổ May 2', 'Tổ ĐG', 'Chuyen 1'})

# Mã IE (WC-* + tổ chuẩn) → bộ phận HR phòng SẢN XUẤT (khớp tên Division đã fold).
_IE_WC_TO_HR_KEYS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (('wc-cut', 'wc-fusing', 'cut', 'fusing', 'cat'), ('cat', 'trai', 'trai vai')),
    (('wc-print', 'print', 'in-ep', 'in_ep', 'in ep', 'ep logo'), ('in ep', 'in-ep')),
    (('theu', 'wc-embroider'), ('theu',)),
    (('wc-sew', 'sew', 'may'), ('may',)),
    (('wc-finish', 'finish', 'ui', 'press', 'ht'), ('ui', 'gap', 'gap xep')),
    (('wc-pack', 'pack', 'gap', 'gh'), ('giao hang', 'thanh pham', 'tp', 'gap')),
    # QC: gắn MAY nếu không có bộ phận QC riêng
    (('wc-qc', 'qc', 'fullcheck'), ('may',)),
)

# SP/người/ngày ước lượng theo loại chuyền (IE chỉnh lại sau trên UI).
_SP_PER_HEAD_RULES: tuple[tuple[tuple[str, ...], Decimal], ...] = (
    (('co dien', 'cơ điện'), Decimal('0')),
    (('may',), Decimal('14')),
    (('cat', 'cắt', 'trai', 'trải'), Decimal('25')),
    (('in ep', 'in ép', 'in nhiet', 'in nhiệt', 'ep logo', 'ép logo', 'in '), Decimal('21')),
    (('ep ',), Decimal('21')),
    (('ui', 'ủi'), Decimal('30')),
    (('gap', 'gấp'), Decimal('35')),
)
_DEFAULT_SP_PER_HEAD = Decimal('12')


def _fold(text: str) -> str:
    raw = unicodedata.normalize('NFD', (text or '').lower())
    raw = ''.join(ch for ch in raw if unicodedata.category(ch) != 'Mn')
    return raw.replace('đ', 'd').strip()


def sp_per_head_for_division(name: str) -> Decimal:
    folded = _fold(name)
    for keys, rate in _SP_PER_HEAD_RULES:
        if any(k in folded for k in keys):
            return rate
    return _DEFAULT_SP_PER_HEAD


def work_center_code_for_division(division_id: int) -> str:
    return f'{CODE_PREFIX}{int(division_id)}'


def hr_work_centers_qs(*, include_inactive_ids: list[int] | None = None):
    """Bộ phận chịu trách nhiệm = tổ HRD-* đồng bộ từ HR phòng SẢN XUẤT."""
    hr_filter = Q(code__istartswith=CODE_PREFIX, is_active=True, is_demo=False)
    extra_ids = [int(x) for x in (include_inactive_ids or []) if x]
    if extra_ids:
        qs = SxWorkCenter.objects.filter(Q(pk__in=extra_ids) | hr_filter).distinct()
    else:
        qs = SxWorkCenter.objects.filter(hr_filter)
    qs = qs.order_by('name', 'code')
    if extra_ids or qs.exists():
        return qs
    return SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by('name', 'code')


def _pick_hr_by_keys(hr_centers: list[SxWorkCenter], hr_keys: tuple[str, ...]) -> SxWorkCenter | None:
    """Ưu tiên tên khớp ngắn/gần đúng (MAY trước MAY (152A…))."""
    hits: list[tuple[int, SxWorkCenter]] = []
    for hc in hr_centers:
        folded_name = _fold(f'{hc.name} {hc.team_label}')
        for key in hr_keys:
            if key == folded_name or folded_name.startswith(key + ' ') or folded_name.startswith(key + '('):
                hits.append((0, hc))
                break
            if key in folded_name:
                hits.append((len(folded_name), hc))
                break
    if not hits:
        return None
    hits.sort(key=lambda x: (x[0], x[1].code))
    return hits[0][1]


def map_ie_center_to_hr(center: SxWorkCenter | None) -> SxWorkCenter | None:
    """Map work center IE (WC-*) sang bộ phận HRD-* nếu có."""
    if center is None:
        return None
    return resolve_work_center_code(center.code) or (
        center if (center.code or '').upper().startswith(CODE_PREFIX) and center.is_active else None
    )


def resolve_work_center_code(code: str | None, *, name_hint: str = '') -> SxWorkCenter | None:
    """Resolve mã WC/HRD (hoặc tên) → bộ phận HRD-* đang active."""
    raw = (code or '').strip()
    hint = (name_hint or '').strip()
    if not raw and not hint:
        return None

    if raw.upper().startswith(CODE_PREFIX):
        return SxWorkCenter.objects.filter(
            code__iexact=raw, is_active=True, is_demo=False,
        ).first()

    # Đã là HRD nhưng viết thường / đã tắt → thử theo mã
    direct = SxWorkCenter.objects.filter(code__iexact=raw).first() if raw else None
    if direct and (direct.code or '').upper().startswith(CODE_PREFIX) and direct.is_active:
        return direct

    needle = _fold(f'{raw} {hint}')
    hr_centers = list(hr_work_centers_qs())
    if not hr_centers:
        return None

    # Map theo bảng IE → HR
    for ie_keys, hr_keys in _IE_WC_TO_HR_KEYS:
        if any(k in needle for k in ie_keys):
            hit = _pick_hr_by_keys(hr_centers, hr_keys)
            if hit:
                return hit

    # Khớp trực tiếp tên bộ phận HR
    for hc in hr_centers:
        folded = _fold(f'{hc.name} {hc.team_label} {hc.code}')
        if needle and (needle == folded or needle in folded or folded in needle):
            return hc
    return None


def remap_ie_master_to_hr() -> dict[str, int]:
    """Gắn lại nhóm công đoạn + dòng routing từ WC IE → bộ phận HRD-*."""
    from san_xuat.ie_models import SxOperationGroup, SxRoutingLine

    stats = {'groups': 0, 'routing_lines': 0}

    for group in SxOperationGroup.objects.select_related('default_work_center').iterator():
        mapped = resolve_work_center_code(
            group.default_work_center_code or (group.default_work_center.code if group.default_work_center_id else ''),
            name_hint=f'{group.process_stage_label} {group.name}',
        )
        if mapped is None:
            continue
        if (
            group.default_work_center_id == mapped.pk
            and (group.default_work_center_code or '') == mapped.code
        ):
            continue
        group.default_work_center = mapped
        group.default_work_center_code = mapped.code
        group.save(update_fields=['default_work_center', 'default_work_center_code', 'updated_at'])
        stats['groups'] += 1

    for line in SxRoutingLine.objects.select_related('work_center').iterator():
        mapped = resolve_work_center_code(
            line.work_center_code or (line.work_center.code if line.work_center_id else ''),
            name_hint=f'{line.group_code} {line.op_name_vi}',
        )
        if mapped is None:
            continue
        if line.work_center_id == mapped.pk and (line.work_center_code or '') == mapped.code:
            continue
        line.work_center = mapped
        line.work_center_code = mapped.code
        line.save(update_fields=['work_center', 'work_center_code'])
        stats['routing_lines'] += 1

    return stats


def _sx_department() -> Department | None:
    for name in SX_DEPT_NAMES:
        dept = Department.objects.filter(name__iexact=name).first()
        if dept:
            return dept
    return Department.objects.filter(name__icontains='SẢN XUẤT').first()


def _is_team_lead_title(job_position: str) -> bool:
    """Chức danh tổ trưởng / trưởng BP — không dùng viết tắt TT (dễ dính 'TT in ép')."""
    pos = _fold(job_position or '')
    return 'truong bo phan' in pos or 'to truong' in pos


def _manager_rank(profile: Profile) -> tuple[int, str, int]:
    """Ưu tiên TBP → tổ trưởng (role + chức danh) → tổ trưởng (chỉ role)."""
    pos = _fold(profile.job_position or '')
    role = profile.role or ''
    titled = 'to truong' in pos or 'truong bo phan' in pos
    if role == ROLE_DIVISION_HEAD or 'truong bo phan' in pos:
        rank = 0
    elif role == ROLE_TEAM_LEADER and titled:
        rank = 1
    elif role == ROLE_TEAM_LEADER:
        rank = 2
    elif titled:
        rank = 3
    else:
        rank = 4
    return (rank, profile.employee_code or '', profile.pk)


def _manager_profile_for_division(division_id: int) -> Profile | None:
    """Trưởng BP / tổ trưởng của bộ phận — vị trí chính + kiêm nhiệm."""
    from hrm.concurrent_positions import heads_for_division
    from hrm.models import ProfileConcurrentPosition

    div = Division.objects.filter(pk=division_id).first()
    if div is None:
        return None
    heads = [
        p for p in heads_for_division(div.department_id, division_id)
        if p.user_id
    ]
    if heads:
        heads.sort(key=_manager_rank)
        return heads[0]

    primary = list(
        Profile.objects.filter(
            division_id=division_id,
            is_employed=True,
            user__is_active=True,
        ).filter(
            Q(role=ROLE_TEAM_LEADER) | Q(role=ROLE_DIVISION_HEAD),
        ).select_related('user')
    )
    titled = list(
        Profile.objects.filter(
            division_id=division_id,
            is_employed=True,
            user__is_active=True,
        ).select_related('user')
    )
    primary.extend(p for p in titled if _is_team_lead_title(p.job_position or '') and p.user_id)

    conc_ids = list(
        ProfileConcurrentPosition.objects.filter(
            is_active=True,
            division_id=division_id,
            profile__is_employed=True,
            profile__user__is_active=True,
        ).filter(
            Q(role__in={ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD})
            | Q(job_position__icontains='Tổ trưởng')
            | Q(job_position__icontains='Trưởng bộ phận'),
        ).values_list('profile_id', flat=True)
    )
    if conc_ids:
        extra = list(
            Profile.objects.filter(pk__in=conc_ids, is_employed=True).select_related('user')
        )
        seen = {p.pk for p in primary}
        for p in extra:
            if p.pk not in seen and p.user_id:
                primary.append(p)

    candidates = [p for p in primary if p.user_id]
    if not candidates:
        return None
    candidates.sort(key=_manager_rank)
    return candidates[0]


def _head_profile(division: Division) -> Profile | None:
    return _manager_profile_for_division(division.pk)


def division_id_from_work_center_code(code: str | None) -> int | None:
    """Parse pk Division từ mã HRD-{id}."""
    raw = (code or '').strip()
    if not raw.upper().startswith(CODE_PREFIX.upper()):
        return None
    suffix = raw[len(CODE_PREFIX) :]
    try:
        return int(suffix)
    except (TypeError, ValueError):
        return None


_WC_CODE_TO_SLUG = {
    'CAT': 'cat',
    'IN-EP': 'inep',
    'THEU': 'theu',
    'MAY': 'may',
    'HT': 'ht',
    'GH': 'gh',
}


def team_slug_for_work_center(center: SxWorkCenter | None) -> str | None:
    """Slug tổ chuẩn (cat/inep/…) từ SxWorkCenter HRD-* hoặc CAT/MAY/…"""
    if center is None:
        return None
    code = (center.code or '').strip().upper()
    if code in _WC_CODE_TO_SLUG:
        return _WC_CODE_TO_SLUG[code]

    did = division_id_from_work_center_code(center.code)
    if did:
        from san_xuat.hub_models import SxTeamDivisionMap

        slug = (
            SxTeamDivisionMap.objects.filter(division_id=did, is_demo=False)
            .order_by('-is_active', 'id')
            .values_list('team_slug', flat=True)
            .first()
        )
        if slug:
            return slug
        div = Division.objects.filter(pk=did).first()
        if div is not None:
            return _team_slug_from_folded(_fold(div.name))
    return _team_slug_from_folded(_fold(f'{center.code} {center.name} {center.team_label}'))


def _team_slug_from_folded(folded: str) -> str | None:
    if not folded:
        return None
    rules: tuple[tuple[tuple[str, ...], str], ...] = (
        (('in-ep', 'in_ep', 'in ep', 'wc-print', 'ep logo'), 'inep'),
        (('giao hang', 'thanh pham', 'wc-pack', 'pack'), 'gh'),
        (('gap xep', 'wc-finish', 'finish'), 'ht'),
        (('wc-embroider', 'theu'), 'theu'),
        (('wc-cut', 'wc-fusing', 'fusing', 'trai vai', 'cat'), 'cat'),
        (('wc-sew', 'sew', 'may'), 'may'),
        (('ui', 'ht'), 'ht'),
        (('gh',), 'gh'),
    )
    for keys, slug in rules:
        if any(k == folded or k in folded for k in keys):
            return slug
    return None


def division_ids_for_work_center(center: SxWorkCenter | None) -> list[int]:
    """Bộ phận HR tương ứng tổ trên form LSX."""
    if center is None:
        return []
    did = division_id_from_work_center_code(center.code)
    if did:
        return [did]

    mapped = map_ie_center_to_hr(center)
    if mapped is not None:
        did = division_id_from_work_center_code(mapped.code)
        if did:
            return [did]

    slug = team_slug_for_work_center(center)
    if not slug:
        return []

    from san_xuat.hub_models import SxTeamDivisionMap

    rows = list(
        SxTeamDivisionMap.objects.filter(team_slug=slug, is_demo=False)
        .order_by('-is_active', 'id')
        .values_list('division_id', 'is_active')
    )
    active = [int(d) for d, is_on in rows if is_on]
    if active:
        return list(dict.fromkeys(active))
    if rows:
        return list(dict.fromkeys(int(d) for d, _ in rows))

    try:
        from san_xuat.services.team_division_map import suggest_maps_from_names

        suggested = suggest_maps_from_names().get(slug) or []
        if suggested:
            return list(dict.fromkeys(int(x) for x in suggested))
    except Exception:
        pass
    return []


def _profile_manager_label(profile: Profile) -> tuple[str, str]:
    name = (profile.full_name or '').strip()
    user = getattr(profile, 'user', None)
    if not name and user is not None:
        name = (user.get_full_name() or user.username or '').strip()
    role = ''
    getter = getattr(profile, 'get_role_display', None)
    if callable(getter):
        role = getter() or ''
    else:
        role = profile.role or ''
    return name, role


def default_manager_user_id_for_work_center(work_center_id: int | None) -> int | None:
    """User pk trưởng BP / tổ trưởng HR tương ứng tổ/bộ phận SxWorkCenter."""
    info = default_manager_info_for_work_center(work_center_id)
    return info.get('id') or None


def default_manager_info_for_work_center(work_center_id: int | None) -> dict:
    """id / label / role quản lý mặc định theo tổ."""
    empty = {'id': '', 'label': '', 'role': ''}
    if not work_center_id:
        return empty
    try:
        center = SxWorkCenter.objects.filter(pk=int(work_center_id)).first()
    except (TypeError, ValueError):
        return empty
    if center is None:
        return empty
    for did in division_ids_for_work_center(center):
        head = _manager_profile_for_division(did)
        if head is None or not head.user_id:
            continue
        label, role = _profile_manager_label(head)
        return {'id': int(head.user_id), 'label': label, 'role': role}
    return empty


def mo_form_work_center_id(
    *,
    work_center=None,
    work_center_id: int | None = None,
    work_center_code: str = '',
    name_hint: str = '',
) -> int | None:
    """ID tổ hiện trên dropdown LSX (HRD-* nếu có, không thì CAT/MAY/…)."""
    center = work_center
    if center is None and work_center_id:
        try:
            center = SxWorkCenter.objects.filter(pk=int(work_center_id)).first()
        except (TypeError, ValueError):
            center = None
    options = list(hr_work_centers_qs())
    option_pks = {int(c.pk) for c in options}
    if center is not None and int(center.pk) in option_pks:
        return int(center.pk)

    code = (work_center_code or (getattr(center, 'code', None) or '')).strip()
    hint = (name_hint or '').strip()
    if not hint and center is not None:
        hint = f'{center.team_label or ""} {center.name or ""}'
    slug = team_slug_for_work_center(center) if center is not None else None
    if not slug:
        slug = _team_slug_from_folded(_fold(f'{code} {hint}'))
    if slug:
        for opt in options:
            if team_slug_for_work_center(opt) == slug:
                return int(opt.pk)

    mapped = resolve_work_center_code(code, name_hint=hint)
    if mapped is not None:
        return int(mapped.pk)
    return int(center.pk) if center is not None else None


def work_center_options_with_default_manager(
    *,
    include_inactive_ids: list[int] | None = None,
) -> list[dict]:
    """Options dropdown tổ LSX: id, label, default_manager_id (TBP / tổ trưởng HR)."""
    centers = list(hr_work_centers_qs(include_inactive_ids=include_inactive_ids))
    rows: list[dict] = []
    for c in centers:
        label = (c.team_label or c.name or c.code or '').strip()
        info = default_manager_info_for_work_center(c.pk)
        rows.append({
            'id': c.pk,
            'label': label,
            'default_manager_id': info['id'] or '',
            'default_manager_label': info['label'] or '',
            'default_manager_role': info['role'] or '',
        })
    return rows


@dataclass
class SyncCapacityResult:
    created: int = 0
    updated: int = 0
    deactivated: int = 0
    hr_maps: int = 0
    skipped: int = 0
    department: str = ''
    centers: list[str] | None = None

    def __post_init__(self):
        if self.centers is None:
            self.centers = []


@transaction.atomic
def sync_capacity_from_hrm(
    *,
    reset_capacity: bool = False,
    deactivate_legacy: bool = True,
    include_support: bool = True,
    deactivate_non_hr: bool = True,
) -> SyncCapacityResult:
    """Tạo/cập nhật SxWorkCenter theo Division phòng SẢN XUẤT trên HR.

    deactivate_non_hr: tắt các tổ không phải HRD-* (WC IE, tổ tay cũ) để danh sách
    bộ phận chỉ còn bộ phận thật từ HR. Mã WC-* vẫn giữ bản ghi cho FK routing IE.
    """
    result = SyncCapacityResult()
    dept = _sx_department()
    if not dept:
        result.skipped = 1
        return result
    result.department = dept.name

    divisions = list(
        Division.objects.filter(department=dept, is_active=True).order_by('sort_order', 'name')
    )
    keep_codes: set[str] = set()
    today = timezone.localdate().isoformat() if hasattr(timezone, 'localdate') else date.today().isoformat()

    for div in divisions:
        staff_qs = Profile.objects.filter(division=div, is_employed=True)
        staff = staff_qs.count()
        folded = _fold(div.name)
        is_support = 'co dien' in folded or 'cơ điện' in _fold(div.name)
        if is_support and not include_support:
            continue

        rate = sp_per_head_for_division(div.name)
        estimated = (Decimal(staff) * rate).quantize(Decimal('0.01'))
        code = work_center_code_for_division(div.pk)
        keep_codes.add(code)
        team_label = (div.name or '').strip()
        notes = (
            f'Đồng bộ HR bộ phận #{div.pk} · headcount={staff} · '
            f'ước NL={staff}×{rate} SP/ngày · {today}'
        )
        if is_support:
            notes = f'[Hỗ trợ] {notes}'

        defaults_common = {
            'name': team_label,
            'team_label': team_label,
            'uom_label': 'SP',
            # Luôn hiện trong chọn bộ phận; NL có thể = 0 nếu chưa có headcount
            'is_active': True,
            'notes': notes,
            'is_demo': False,
            # P3: số nhân sự để tính phút khả dụng khi xếp lịch theo SMV
            'headcount': staff,
        }

        center = SxWorkCenter.objects.filter(code__iexact=code).first()
        if center is None:
            center = SxWorkCenter.objects.create(
                code=code,
                capacity_per_day=estimated,
                **defaults_common,
            )
            result.created += 1
        else:
            center.name = defaults_common['name']
            center.team_label = defaults_common['team_label']
            center.uom_label = defaults_common['uom_label']
            center.is_active = defaults_common['is_active']
            center.notes = defaults_common['notes']
            center.is_demo = False
            center.headcount = staff
            if reset_capacity or center.capacity_per_day is None or center.capacity_per_day <= 0:
                center.capacity_per_day = estimated
            center.save()
            result.updated += 1

        result.centers.append(
            f'{code} {team_label} staff={staff} cap={center.capacity_per_day}'
        )

        head = _head_profile(div)
        emp_code = ''
        emp_name = team_label
        if head:
            emp_code = (head.employee_code or head.user.username or '').strip()
            emp_name = (
                (head.full_name or '').strip()
                or head.user.get_full_name()
                or head.user.username
            )
        SxTeamHrMap.objects.update_or_create(
            team_label=team_label,
            defaults={
                'employee_code': emp_code[:40],
                'employee_name': (emp_name or team_label)[:120],
                'notes': f'HR div #{div.pk}',
                'is_active': True,
                'is_demo': False,
            },
        )
        result.hr_maps += 1

    # Tắt tổ HRD-* không còn trong HR
    stale = SxWorkCenter.objects.filter(code__istartswith=CODE_PREFIX).exclude(
        code__in=keep_codes
    )
    result.deactivated += stale.update(is_active=False)

    if deactivate_legacy:
        legacy_qs = SxWorkCenter.objects.filter(code__in=LEGACY_FAKE_CODES)
        result.deactivated += legacy_qs.count()
        legacy_qs.delete()
        SxTeamHrMap.objects.filter(team_label__in=LEGACY_FAKE_TEAMS).delete()

    if deactivate_non_hr:
        # Giữ 6 tổ chuẩn (Cắt…GH) đang dùng trên Năng lực / Công việc tổ;
        # chỉ tắt tổ tay / mã lẻ khác — HRD-* vẫn quản lý riêng.
        from san_xuat.services.progress_template import standard_work_center_codes

        non_hr = (
            SxWorkCenter.objects.filter(is_demo=False, is_active=True)
            .exclude(code__istartswith=CODE_PREFIX)
            .exclude(code__in=standard_work_center_codes())
        )
        result.deactivated += non_hr.update(is_active=False)

    # Đồng bộ headcount / NL ước lượng từ bộ phận HR → 6 tổ chuẩn (nếu map được)
    _apply_hr_headcount_to_standard_centers()

    return result


def _apply_hr_headcount_to_standard_centers() -> int:
    """Gán headcount + capacity từ HRD-* khớp tên vào CAT / IN-EP / …"""
    from san_xuat.services.order_progress_sheet import ensure_progress_work_centers
    from san_xuat.services.progress_template import (
        WC_CAT,
        WC_GH,
        WC_HT,
        WC_IN_EP,
        WC_MAY,
        WC_THEU,
    )

    ensure_progress_work_centers()
    hr_centers = list(hr_work_centers_qs())
    if not hr_centers:
        return 0
    mapping: tuple[tuple[str, tuple[str, ...]], ...] = (
        (WC_CAT, ('cat', 'trai', 'trai vai')),
        (WC_IN_EP, ('in ep', 'in ', 'ep logo', 'ep ')),
        (WC_THEU, ('theu',)),
        (WC_MAY, ('may',)),
        (WC_HT, ('ui', 'gap', 'gap xep')),
        (WC_GH, ('giao hang', 'thanh pham', 'tp')),
    )
    updated = 0
    for code, keys in mapping:
        hc = _pick_hr_by_keys(hr_centers, keys)
        wc = SxWorkCenter.objects.filter(code=code, is_demo=False).first()
        if not hc or not wc:
            continue
        fields: list[str] = []
        if (wc.headcount or 0) != (hc.headcount or 0):
            wc.headcount = hc.headcount or 0
            fields.append('headcount')
        if (hc.capacity_per_day or 0) > 0 and (
            not wc.capacity_per_day or wc.capacity_per_day <= 0
        ):
            wc.capacity_per_day = hc.capacity_per_day
            fields.append('capacity_per_day')
        if not wc.is_active:
            wc.is_active = True
            fields.append('is_active')
        if fields:
            wc.save(update_fields=fields)
            updated += 1
    return updated


def remap_process_steps_to_hr() -> int:
    """Gắn lại ProcessStep.work_center từ WC IE → bộ phận HRD-* (nếu map được)."""
    from san_xuat.models import ProcessStep

    updated = 0
    qs = (
        ProcessStep.objects.filter(work_center__isnull=False)
        .exclude(work_center__code__istartswith=CODE_PREFIX)
        .select_related('work_center')
    )
    for step in qs.iterator():
        mapped = map_ie_center_to_hr(step.work_center)
        if mapped and mapped.pk != step.work_center_id:
            step.work_center = mapped
            step.save(update_fields=['work_center'])
            updated += 1
    return updated


def remap_all_to_hr() -> dict[str, int]:
    """Đồng bộ lại toàn bộ tham chiếu bộ phận (BOM + IE) sang HRD-*."""
    ie = remap_ie_master_to_hr()
    return {
        'process_steps': remap_process_steps_to_hr(),
        'groups': ie['groups'],
        'routing_lines': ie['routing_lines'],
    }
