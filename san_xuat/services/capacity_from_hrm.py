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


def map_ie_center_to_hr(center: SxWorkCenter | None) -> SxWorkCenter | None:
    """Map work center IE (WC-*) sang bộ phận HRD-* nếu có."""
    if center is None:
        return None
    if (center.code or '').upper().startswith(CODE_PREFIX):
        return center if center.is_active else None

    needle = _fold(f'{center.code} {center.name} {center.team_label}')
    hr_centers = list(
        SxWorkCenter.objects.filter(
            code__istartswith=CODE_PREFIX,
            is_active=True,
            is_demo=False,
        )
    )
    if not hr_centers:
        return None

    for ie_keys, hr_keys in _IE_WC_TO_HR_KEYS:
        if not any(k in needle for k in ie_keys):
            continue
        for hc in hr_centers:
            folded_name = _fold(f'{hc.name} {hc.team_label}')
            if any(k in folded_name for k in hr_keys):
                return hc
    return None


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
    # 1) Vai trò tổ trưởng / trưởng bộ phận
    for role in (ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD):
        hit = qs.filter(role=role).first()
        if hit:
            return hit
    # 2) Chức danh chứa tổ trưởng / TT
    for p in qs:
        pos = _fold(p.job_position or '')
        if 'to truong' in pos or pos.startswith('tt ') or '(tt ' in pos or ' tt ' in pos:
            return p
    return None


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
