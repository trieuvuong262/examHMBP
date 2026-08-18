"""Quản lý nhân sự theo tổ — roster từ map bộ phận + hồ sơ năng lực."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from hrm.concurrent_positions import effective_roles, get_active_concurrent_positions
from hrm.permissions import (
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_TEAM_LEADER,
)
from san_xuat.hub_models import (
    SxMoProcessAssignee,
    SxProductionOrder,
    SxTeamPersonnelSkill,
    SxTeamWorkClose,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services.progress_template import steps_for_group, team_by_slug
from san_xuat.services.production_machines import format_machine_codes_display, machine_options_for_codes
from san_xuat.services.team_division_map import (
    has_mapped_divisions,
    mapped_division_ids,
    users_in_mapped_divisions,
)

User = get_user_model()

SKILL_LEVELS = ('A', 'B', 'C')
OUTPUT_LOOKBACK_DAYS = 14
_MANAGER_ROLES = {ROLE_DIRECTOR, ROLE_DEPARTMENT_HEAD, ROLE_DIVISION_HEAD}


@dataclass
class TeamPersonnelProcessItem:
    key: str
    label: str
    avg_qty: str = ''


@dataclass
class TeamPersonnelSkillView:
    process_keys: list[str] = field(default_factory=list)
    process_labels: list[str] = field(default_factory=list)
    process_items: list[TeamPersonnelProcessItem] = field(default_factory=list)
    process_avg_qty: dict[str, str] = field(default_factory=dict)
    skill_level: str = ''
    machines: str = ''
    machine_codes: list[str] = field(default_factory=list)
    is_multiskill: bool = False
    notes: str = ''
    updated_at: object | None = None
    updated_by_label: str = ''


@dataclass
class TeamPersonnelRow:
    user_id: int
    username: str
    full_name: str
    employee_code: str
    phone: str
    avatar_url: str
    department: str
    division: str
    concurrent_labels: list[str]
    job_position: str
    job_title: str
    role: str
    role_label: str
    is_probation: bool
    join_date: object | None
    gender: str
    skill: TeamPersonnelSkillView
    open_jobs: int = 0
    open_steps: int = 0
    closed_jobs: int = 0
    reports_14d: int = 0
    qty_14d: Decimal = field(default_factory=lambda: Decimal('0'))
    missing_skill: bool = True


@dataclass
class TeamPersonnelBoard:
    team: dict
    rows: list[TeamPersonnelRow]
    step_defs: list
    mapped: bool
    total: int = 0
    busy: int = 0
    idle: int = 0
    probation: int = 0
    missing_skill: int = 0


def _person_label(user) -> str:
    if not user:
        return ''
    p = getattr(user, 'profile', None)
    label = ((getattr(p, 'full_name', None) or '') if p else '').strip()
    return label or user.get_full_name() or user.username


def user_team_division_ids(user) -> set[int]:
    p = getattr(user, 'profile', None)
    if p is None:
        return set()
    ids: set[int] = set()
    if p.division_id:
        ids.add(int(p.division_id))
    for slot in get_active_concurrent_positions(p):
        if slot.division_id:
            ids.add(int(slot.division_id))
    return ids


def can_edit_team_personnel(user, slug: str) -> bool:
    """Tổ trưởng của tổ (bộ phận đã map) hoặc TBP / TP / GD / superuser."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if not team_by_slug(slug):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    roles = effective_roles(user)
    if roles & _MANAGER_ROLES:
        return True
    if ROLE_TEAM_LEADER in roles:
        mapped = mapped_division_ids(slug)
        return bool(mapped and (user_team_division_ids(user) & mapped))
    return False


def _normalize_process_keys(raw, *, allowed: set[str]) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [raw]
    else:
        items = list(raw)
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = str(item or '').strip()
        if not key or key not in allowed or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _normalize_process_avg_qty(raw, *, allowed: set[str], selected_keys: list[str]) -> dict[str, str]:
    """Chuẩn hóa SL trung bình — chỉ lưu cho công đoạn đang chọn."""
    selected = set(selected_keys)
    if isinstance(raw, dict):
        items = raw.items()
    else:
        items = []
    out: dict[str, str] = {}
    for key, value in items:
        k = str(key or '').strip()
        if not k or k not in allowed or k not in selected:
            continue
        text = str(value or '').strip().replace(',', '.')
        if not text:
            continue
        try:
            qty = Decimal(text)
        except InvalidOperation:
            continue
        if qty < 0:
            continue
        normalized = format(qty.normalize(), 'f')
        if '.' in normalized:
            normalized = normalized.rstrip('0').rstrip('.')
        out[k] = normalized or '0'
    return out


def parse_process_avg_qty_post(post, *, allowed: set[str]) -> dict[str, str]:
    """Đọc input `process_avg_qty_<key>` từ form modal năng lực."""
    raw: dict[str, str] = {}
    prefix = 'process_avg_qty_'
    for key in allowed:
        value = (post.get(f'{prefix}{key}') or '').strip()
        if value:
            raw[key] = value
    return raw


def _process_items(keys: list[str], label_by_key: dict[str, str], avg_map: dict[str, str]) -> list[TeamPersonnelProcessItem]:
    return [
        TeamPersonnelProcessItem(
            key=key,
            label=label_by_key.get(key, key),
            avg_qty=avg_map.get(key, ''),
        )
        for key in keys
        if key in label_by_key or key
    ]


def _normalize_skill_level(raw: str) -> str:
    value = (raw or '').strip().upper()
    if value in SKILL_LEVELS:
        return value
    return ''


def _normalize_machine_codes(raw) -> str:
    """Chuẩn hóa danh sách mã máy từ form — lưu CSV trong CharField."""
    if raw is None:
        tokens: list[str] = []
    elif isinstance(raw, str):
        tokens = [part.strip() for part in raw.replace(';', ',').split(',') if part.strip()]
    else:
        tokens = [str(part or '').strip() for part in raw if str(part or '').strip()]
    if not tokens:
        return ''
    valid = {item['code'].casefold(): item['code'] for item in machine_options_for_codes(tokens)}
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(valid.get(key, token))
    return ', '.join(out)[:255]


@transaction.atomic
def upsert_team_personnel_skill(
    *,
    slug: str,
    user_id: int,
    process_keys=None,
    process_avg_qty=None,
    skill_level: str = '',
    machines: str = '',
    is_multiskill: bool = False,
    notes: str = '',
    updated_by=None,
) -> SxTeamPersonnelSkill:
    team = team_by_slug(slug)
    if not team:
        raise PlanningError('Tổ không hợp lệ.')
    machines = _normalize_machine_codes(machines)
    pool_ids = set(users_in_mapped_divisions(slug).values_list('pk', flat=True))
    if int(user_id) not in pool_ids:
        raise PlanningError('Nhân viên không thuộc bộ phận đã map vào tổ này.')
    allowed = {s.key for s in steps_for_group(team['group_key'])}
    keys = _normalize_process_keys(process_keys, allowed=allowed)
    avg_qty = _normalize_process_avg_qty(process_avg_qty or {}, allowed=allowed, selected_keys=keys)
    level = _normalize_skill_level(skill_level)
    actor = updated_by if getattr(updated_by, 'is_authenticated', False) else None
    rec, created = SxTeamPersonnelSkill.objects.select_for_update().get_or_create(
        user_id=int(user_id),
        team_slug=team['slug'],
        defaults={
            'process_keys': keys,
            'process_avg_qty': avg_qty,
            'skill_level': level,
            'machines': machines,
            'is_multiskill': bool(is_multiskill),
            'notes': (notes or '').strip(),
            'is_demo': False,
            'created_by': actor,
            'updated_by': actor,
        },
    )
    if created:
        return rec
    rec.process_keys = keys
    rec.process_avg_qty = avg_qty
    rec.skill_level = level
    rec.machines = machines
    rec.is_multiskill = bool(is_multiskill)
    rec.notes = (notes or '').strip()
    rec.is_demo = False
    rec.updated_by = actor
    rec.save(update_fields=[
        'process_keys',
        'process_avg_qty',
        'skill_level',
        'machines',
        'is_multiskill',
        'notes',
        'is_demo',
        'updated_by',
        'updated_at',
    ])
    return rec


def _assignment_stats(*, slug: str, user_ids: list[int], labels: list[str]) -> dict[int, dict[str, int]]:
    stats: dict[int, dict[str, int]] = {
        uid: {'open_jobs': 0, 'open_steps': 0, 'closed_jobs': 0} for uid in user_ids
    }
    if not user_ids or not labels:
        return stats
    q = Q()
    for label in labels:
        q |= Q(mo_process_step__process_name__iexact=label)
    rows = list(
        SxMoProcessAssignee.objects.filter(q, user_id__in=user_ids)
        .filter(mo_process_step__production_order__is_demo=False)
        .exclude(
            mo_process_step__production_order__status__in=(
                SxProductionOrder.STATUS_DRAFT,
                SxProductionOrder.STATUS_CANCELLED,
            ),
        )
        .values_list('user_id', 'mo_process_step__production_order_id')
    )
    if not rows:
        return stats
    mo_ids = {mo_id for _uid, mo_id in rows if mo_id}
    closed = set(
        SxTeamWorkClose.objects.filter(
            team_slug=slug,
            is_demo=False,
            production_order_id__in=mo_ids,
        ).values_list('production_order_id', flat=True)
    )
    open_mos: dict[int, set[int]] = defaultdict(set)
    closed_mos: dict[int, set[int]] = defaultdict(set)
    open_steps: dict[int, int] = defaultdict(int)
    for uid, mo_id in rows:
        if mo_id in closed:
            closed_mos[uid].add(mo_id)
        else:
            open_mos[uid].add(mo_id)
            open_steps[uid] += 1
    for uid in user_ids:
        stats[uid] = {
            'open_jobs': len(open_mos.get(uid, ())),
            'open_steps': open_steps.get(uid, 0),
            'closed_jobs': len(closed_mos.get(uid, ())),
        }
    return stats


def _output_stats(*, user_ids: list[int], since) -> dict[int, dict]:
    empty = {'reports_14d': 0, 'qty_14d': Decimal('0')}
    stats = {uid: dict(empty) for uid in user_ids}
    if not user_ids:
        return stats
    from reports.models import DailyWorkReport, DailyWorkReportLine, ProductionShiftProduct

    from django.db.models import Count

    submitted = DailyWorkReport.STATUS_SUBMITTED
    report_counts = (
        DailyWorkReport.objects.filter(
            employee_id__in=user_ids,
            status=submitted,
            report_date__gte=since,
        )
        .values('employee_id')
        .annotate(n=Count('id'))
    )
    for row in report_counts:
        stats[row['employee_id']]['reports_14d'] = int(row['n'] or 0)

    shift_qty = (
        ProductionShiftProduct.objects.filter(
            report__employee_id__in=user_ids,
            report__status=submitted,
            report__report_date__gte=since,
        )
        .values('report__employee_id')
        .annotate(qty=Sum('total_quantity'))
    )
    used_shift = False
    for row in shift_qty:
        qty = Decimal(str(row['qty'] or 0))
        if qty:
            used_shift = True
        stats[row['report__employee_id']]['qty_14d'] = qty
    if used_shift:
        return stats

    line_qty = (
        DailyWorkReportLine.objects.filter(
            report__employee_id__in=user_ids,
            report__status=submitted,
            report__report_date__gte=since,
        )
        .values('report__employee_id')
        .annotate(qty=Sum('quantity'))
    )
    for row in line_qty:
        stats[row['report__employee_id']]['qty_14d'] = Decimal(str(row['qty'] or 0))
    return stats


def build_team_personnel_board(*, slug: str, search: str = '') -> TeamPersonnelBoard:
    team = team_by_slug(slug)
    if not team:
        raise PlanningError('Tổ không hợp lệ.')
    step_defs = steps_for_group(team['group_key'])
    label_by_key = {s.key: s.label for s in step_defs}
    mapped = has_mapped_divisions(slug)
    qs = users_in_mapped_divisions(slug).select_related(
        'profile__department',
        'profile__division',
    ).prefetch_related('profile__concurrent_positions__division')
    term = (search or '').strip()
    if term:
        qs = qs.filter(
            Q(username__icontains=term)
            | Q(profile__full_name__icontains=term)
            | Q(profile__employee_code__icontains=term)
            | Q(profile__phone__icontains=term)
            | Q(profile__job_position__icontains=term)
            | Q(profile__job_title__icontains=term)
        )
    users = list(qs)
    user_ids = [u.pk for u in users]
    skills = {
        rec.user_id: rec
        for rec in SxTeamPersonnelSkill.objects.filter(
            team_slug=team['slug'],
            user_id__in=user_ids,
            is_demo=False,
        ).select_related('updated_by', 'updated_by__profile')
    }
    assign = _assignment_stats(
        slug=team['slug'],
        user_ids=user_ids,
        labels=[s.label for s in step_defs],
    )
    since = timezone.localdate() - timedelta(days=OUTPUT_LOOKBACK_DAYS - 1)
    output = _output_stats(user_ids=user_ids, since=since)

    rows: list[TeamPersonnelRow] = []
    for user in users:
        profile = getattr(user, 'profile', None)
        skill_rec = skills.get(user.pk)
        keys = skill_rec.process_key_list() if skill_rec else []
        raw_machines = (skill_rec.machines if skill_rec else '') or ''
        machine_opts = machine_options_for_codes(raw_machines)
        avg_map = skill_rec.process_avg_qty_map() if skill_rec else {}
        skill_view = TeamPersonnelSkillView(
            process_keys=keys,
            process_labels=[label_by_key[k] for k in keys if k in label_by_key],
            process_items=_process_items(keys, label_by_key, avg_map),
            process_avg_qty=avg_map,
            skill_level=(skill_rec.skill_level if skill_rec else '') or '',
            machines=format_machine_codes_display(raw_machines),
            machine_codes=[item['code'] for item in machine_opts],
            is_multiskill=bool(skill_rec and skill_rec.is_multiskill),
            notes=(skill_rec.notes if skill_rec else '') or '',
            updated_at=skill_rec.updated_at if skill_rec else None,
            updated_by_label=_person_label(skill_rec.updated_by) if skill_rec else '',
        )
        concurrent_labels = []
        if profile:
            for slot in get_active_concurrent_positions(profile):
                name = (getattr(slot.division, 'name', '') or '').strip()
                if name:
                    concurrent_labels.append(name)
        load = assign.get(user.pk) or {}
        out = output.get(user.pk) or {}
        missing = not (
            skill_view.process_keys or skill_view.skill_level or skill_view.machine_codes or skill_view.notes
        )
        avatar_url = ''
        if profile and getattr(profile, 'avatar', None):
            try:
                avatar_url = profile.avatar.url or ''
            except (ValueError, OSError):
                avatar_url = ''
        phone = ''
        if profile:
            phone = (getattr(profile, 'phone_display', None) or profile.phone or '').strip()
        rows.append(
            TeamPersonnelRow(
                user_id=user.pk,
                username=user.username,
                full_name=((getattr(profile, 'full_name', None) or '') if profile else '').strip()
                or user.get_full_name()
                or user.username,
                employee_code=((getattr(profile, 'employee_code', None) or '') if profile else '').strip(),
                phone=phone,
                avatar_url=avatar_url,
                department=((getattr(getattr(profile, 'department', None), 'name', '') or '') if profile else ''),
                division=((getattr(getattr(profile, 'division', None), 'name', '') or '') if profile else ''),
                concurrent_labels=concurrent_labels,
                job_position=((getattr(profile, 'job_position', None) or '') if profile else ''),
                job_title=((getattr(profile, 'job_title', None) or '') if profile else ''),
                role=((getattr(profile, 'role', None) or '') if profile else ''),
                role_label=(profile.get_role_display() if profile else ''),
                is_probation=bool(profile and profile.on_probation),
                join_date=getattr(profile, 'join_date', None) if profile else None,
                gender=(profile.get_gender_display_short() if profile else ''),
                skill=skill_view,
                open_jobs=int(load.get('open_jobs') or 0),
                open_steps=int(load.get('open_steps') or 0),
                closed_jobs=int(load.get('closed_jobs') or 0),
                reports_14d=int(out.get('reports_14d') or 0),
                qty_14d=Decimal(str(out.get('qty_14d') or 0)),
                missing_skill=missing,
            )
        )

    busy = sum(1 for r in rows if r.open_jobs > 0)
    return TeamPersonnelBoard(
        team=team,
        rows=rows,
        step_defs=step_defs,
        mapped=mapped,
        total=len(rows),
        busy=busy,
        idle=len(rows) - busy,
        probation=sum(1 for r in rows if r.is_probation),
        missing_skill=sum(1 for r in rows if r.missing_skill),
    )
