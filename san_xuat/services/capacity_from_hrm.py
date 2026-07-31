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

# Mã IE (WC-*) → bộ phận HR phòng SẢN XUẤT (khớp tên Division đã fold).
_IE_WC_TO_HR_KEYS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (('wc-cut', 'wc-fusing', 'cut', 'fusing'), ('cat', 'trai', 'trai vai')),
    (('wc-print', 'print', 'ep'), ('in ep', 'in ')),
    (('wc-sew', 'sew', 'may'), ('may',)),
    (('wc-finish', 'finish', 'ui', 'press'), ('ui',)),
    (('wc-pack', 'pack', 'gap'), ('gap', 'gap xep')),
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
    qs = SxWorkCenter.objects.filter(
        code__istartswith=CODE_PREFIX,
        is_active=True,
        is_demo=False,
    )
    extra_ids = [int(x) for x in (include_inactive_ids or []) if x]
    if extra_ids:
        qs = SxWorkCenter.objects.filter(
            Q(pk__in=extra_ids)
            | Q(code__istartswith=CODE_PREFIX, is_active=True, is_demo=False)
        ).distinct()
    return qs.order_by('name', 'code')


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


def _head_profile(division: Division) -> Profile | None:
    qs = (
        Profile.objects.filter(division=division, is_employed=True)
        .select_related('user')
        .order_by('pk')
    )
    # 1) Trưởng bộ phận trước, rồi tổ trưởng
    for role in (ROLE_DIVISION_HEAD, ROLE_TEAM_LEADER):
        hit = qs.filter(role=role).first()
        if hit:
            return hit
    # 2) Chức danh chứa tổ trưởng / TT / trưởng bộ phận
    for p in qs:
        pos = _fold(p.job_position or '')
        if (
            'truong bo phan' in pos
            or 'to truong' in pos
            or pos.startswith('tt ')
            or '(tt ' in pos
            or ' tt ' in pos
        ):
            return p
    return None


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


def default_manager_user_id_for_work_center(work_center_id: int | None) -> int | None:
    """User pk trưởng bộ phận (HR) tương ứng tổ/bộ phận SxWorkCenter."""
    if not work_center_id:
        return None
    center = SxWorkCenter.objects.filter(pk=int(work_center_id)).first()
    if center is None:
        return None
    if not (center.code or '').upper().startswith(CODE_PREFIX.upper()):
        mapped = map_ie_center_to_hr(center)
        if mapped is None:
            return None
        center = mapped
    div_id = division_id_from_work_center_code(center.code)
    if not div_id:
        return None
    div = Division.objects.filter(pk=div_id).first()
    if div is None:
        return None
    head = _head_profile(div)
    if head is None or not head.user_id:
        return None
    return int(head.user_id)


def work_center_options_with_default_manager(
    *,
    include_inactive_ids: list[int] | None = None,
) -> list[dict]:
    """Options dropdown tổ LSX: id, label, default_manager_id (trưởng BP HR)."""
    centers = list(hr_work_centers_qs(include_inactive_ids=include_inactive_ids))
    div_ids: list[int] = []
    center_div: dict[int, int] = {}
    for c in centers:
        div_id = division_id_from_work_center_code(c.code)
        if div_id:
            center_div[c.pk] = div_id
            div_ids.append(div_id)
    head_by_div: dict[int, int] = {}
    if div_ids:
        uniq = list(dict.fromkeys(div_ids))
        profiles = (
            Profile.objects.filter(division_id__in=uniq, is_employed=True)
            .select_related('user')
            .order_by('pk')
        )
        by_div: dict[int, list[Profile]] = {}
        for p in profiles:
            by_div.setdefault(p.division_id, []).append(p)
        for div_id, plist in by_div.items():
            head = None
            for role in (ROLE_DIVISION_HEAD, ROLE_TEAM_LEADER):
                head = next((p for p in plist if p.role == role and p.user_id), None)
                if head:
                    break
            if head is None:
                for p in plist:
                    if not p.user_id:
                        continue
                    pos = _fold(p.job_position or '')
                    if (
                        'truong bo phan' in pos
                        or 'to truong' in pos
                        or pos.startswith('tt ')
                        or '(tt ' in pos
                        or ' tt ' in pos
                    ):
                        head = p
                        break
            if head and head.user_id:
                head_by_div[div_id] = int(head.user_id)
    rows: list[dict] = []
    for c in centers:
        label = (c.team_label or c.name or c.code or '').strip()
        div_id = center_div.get(c.pk)
        mgr_id = head_by_div.get(div_id) if div_id else None
        rows.append({
            'id': c.pk,
            'label': label,
            'default_manager_id': mgr_id or '',
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
        # Giữ bản ghi WC-* / tổ tay cho FK, nhưng tắt để không hiện chọn bộ phận
        non_hr = SxWorkCenter.objects.filter(is_demo=False, is_active=True).exclude(
            code__istartswith=CODE_PREFIX
        )
        result.deactivated += non_hr.update(is_active=False)

    return result


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
