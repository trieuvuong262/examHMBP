"""Công việc tổ — hàng đợi CD theo bộ phận (mẫu cố định)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch

from san_xuat.hub_models import (
    SxMoProcessAssignee,
    SxMoProcessStep,
    SxProductionOrder,
    SxProductionOrderLine,
    SxProductionStat,
    SxTeamWorkClose,
)
from san_xuat.services.order_progress_sheet import (
    _q,
    _size_plans,
    ensure_progress_work_centers,
    work_center_map,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services.progress_template import (
    ProgressStepDef,
    steps_for_group,
    team_by_slug,
)


@dataclass
class TeamWorkRow:
    mo: SxProductionOrder
    step_def: ProgressStepDef
    mo_step: SxMoProcessStep | None
    assignees: list = field(default_factory=list)
    status: str = ''
    plan_qty: Decimal = field(default_factory=lambda: Decimal('0'))
    done_qty: Decimal = field(default_factory=lambda: Decimal('0'))
    remain_qty: Decimal = field(default_factory=lambda: Decimal('0'))


@dataclass
class TeamWorkJob:
    mo: SxProductionOrder
    rows: list[TeamWorkRow]
    step_count: int = 0
    assigned_count: int = 0
    done_count: int = 0
    run_count: int = 0
    wait_count: int = 0
    plan_qty: Decimal = field(default_factory=lambda: Decimal('0'))
    closed: bool = False
    closed_at: object | None = None
    closed_by_label: str = ''


def group_team_work_jobs(rows: list[TeamWorkRow]) -> list[TeamWorkJob]:
    """Gom CD theo LSX — mỗi LSX là một việc."""
    jobs: list[TeamWorkJob] = []
    by_mo: dict[int, TeamWorkJob] = {}
    for row in rows:
        job = by_mo.get(row.mo.pk)
        if job is None:
            job = TeamWorkJob(mo=row.mo, rows=[], plan_qty=row.plan_qty)
            by_mo[row.mo.pk] = job
            jobs.append(job)
        job.rows.append(row)
        job.step_count += 1
        if row.assignees:
            job.assigned_count += 1
        if row.status == 'done':
            job.done_count += 1
        elif row.status == 'in_progress':
            job.run_count += 1
        else:
            job.wait_count += 1
    return jobs


def _step_qty_for_mo(
    mo: SxProductionOrder,
    *,
    sizes,
    stats: list[SxProductionStat],
    label_map: dict[str, ProgressStepDef],
    step_key: str,
) -> tuple[Decimal, Decimal, Decimal]:
    if not sizes:
        plan = _q(mo.qty)
        return plan, Decimal('0'), plan
    size_set = {r.size_label for r in sizes}
    single_total = len(sizes) == 1 and sizes[0].size_label == 'Tổng'
    done_map: dict[str, Decimal] = {}
    for st in stats:
        step = label_map.get((st.process_name or '').strip().casefold())
        if not step or step.key != step_key:
            continue
        size = (st.size_label or '').strip()
        if single_total:
            size = 'Tổng'
        elif not size:
            continue
        elif size not in size_set and size_set:
            continue
        qty = _q(st.qty_good)
        if qty > 0:
            done_map[size] = done_map.get(size, Decimal('0')) + qty
    plan = Decimal('0')
    done = Decimal('0')
    remain = Decimal('0')
    for row in sizes:
        plan += row.qty
        row_done = done_map.get(row.size_label, Decimal('0'))
        row_remain = row.qty - row_done
        if row_remain < 0:
            row_remain = Decimal('0')
        done += row_done
        remain += row_remain
    if plan <= 0:
        plan = _q(mo.qty)
    return plan, done, remain


def _batch_stats_by_mo(mo_ids: list[int]) -> dict[int, list[SxProductionStat]]:
    out: dict[int, list[SxProductionStat]] = {pk: [] for pk in mo_ids}
    if not mo_ids:
        return out
    for st in SxProductionStat.objects.filter(
        production_order_id__in=mo_ids,
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
    ).only('production_order_id', 'process_name', 'size_label', 'qty_good'):
        out.setdefault(st.production_order_id, []).append(st)
    return out


def build_team_work_rows(*, slug: str, search: str = '') -> tuple[dict, list[TeamWorkRow]]:
    team = team_by_slug(slug)
    if not team:
        raise PlanningError('Tổ không hợp lệ.')
    ensure_progress_work_centers()
    step_defs = steps_for_group(team['group_key'])
    labels = {(s.label or '').strip().casefold(): s for s in step_defs}
    label_set = set(labels.keys())

    qs = (
        SxProductionOrder.objects.filter(is_demo=False)
        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .exclude(status=SxProductionOrder.STATUS_DRAFT)
        .select_related('sales_order')
        .prefetch_related(
            Prefetch(
                'lines',
                queryset=SxProductionOrderLine.objects.order_by('size_label', 'id'),
            ),
            Prefetch(
                'mo_process_steps',
                queryset=SxMoProcessStep.objects.select_related('work_center').prefetch_related(
                    'assignees__user__profile',
                ),
            ),
        )
        .order_by('-order_date', '-pk')
    )
    term = (search or '').strip()
    if term:
        from django.db.models import Q

        qs = qs.filter(
            Q(code__icontains=term)
            | Q(product_code__icontains=term)
            | Q(product_name__icontains=term)
            | Q(sales_order__code__icontains=term)
        )

    mos = list(qs[:80])
    mo_ids = [m.pk for m in mos]
    stats_by_mo = _batch_stats_by_mo(mo_ids)
    from san_xuat.services.progress_template import progress_steps

    all_step_label_map = {s.label.casefold(): s for s in progress_steps()}

    rows: list[TeamWorkRow] = []
    for mo in mos:
        sizes = _size_plans(mo)
        mo_stats = stats_by_mo.get(mo.pk, [])
        by_name: dict[str, SxMoProcessStep] = {}
        for st in mo.mo_process_steps.all():
            key = (st.process_name or '').strip().casefold()
            if key in label_set and key not in by_name:
                by_name[key] = st

        for sd in step_defs:
            lk = sd.label.casefold()
            mo_step = by_name.get(lk)
            assignees = []
            status = ''
            if mo_step:
                status = mo_step.status or ''
                for a in mo_step.assignees.all():
                    u = a.user
                    p = getattr(u, 'profile', None)
                    label = ((getattr(p, 'full_name', None) or '') if p else '').strip()
                    label = label or u.get_full_name() or u.username
                    assignees.append({'id': u.pk, 'label': label})
            plan_qty, done_qty, remain_qty = _step_qty_for_mo(
                mo,
                sizes=sizes,
                stats=mo_stats,
                label_map=all_step_label_map,
                step_key=sd.key,
            )
            rows.append(
                TeamWorkRow(
                    mo=mo,
                    step_def=sd,
                    mo_step=mo_step,
                    assignees=assignees,
                    status=status,
                    plan_qty=plan_qty,
                    done_qty=done_qty,
                    remain_qty=remain_qty,
                )
            )
    return team, rows


def ensure_mo_step_for_template(
    *,
    mo: SxProductionOrder,
    step_def: ProgressStepDef,
) -> SxMoProcessStep:
    existing = (
        SxMoProcessStep.objects.filter(
            production_order=mo,
            process_name__iexact=step_def.label,
        )
        .order_by('sequence', 'id')
        .first()
    )
    if existing:
        return existing
    wc_map = work_center_map()
    wc = wc_map.get(step_def.work_center_code)
    max_seq = (
        SxMoProcessStep.objects.filter(production_order=mo)
        .order_by('-sequence')
        .values_list('sequence', flat=True)
        .first()
    ) or 0
    step = SxMoProcessStep.objects.create(
        production_order=mo,
        sequence=max(int(max_seq) + 10, step_def.sequence),
        process_name=step_def.label,
        work_center=wc,
        status=SxMoProcessStep.STATUS_PENDING,
    )
    return step


def _team_slug_for_process_key(process_key: str) -> str | None:
    from san_xuat.services.progress_template import TEAM_SLUGS, step_by_key

    sd = step_by_key(process_key)
    if not sd:
        return None
    for slug, group_key, _menu, _label in TEAM_SLUGS:
        if group_key == sd.group:
            return slug
    return None


@transaction.atomic
def assign_team_work(
    *,
    mo_id: int,
    process_key: str,
    user_ids: list[int],
    assigned_by=None,
    team_slug: str | None = None,
) -> SxMoProcessStep:
    from san_xuat.services.progress_template import step_by_key
    from san_xuat.services.team_division_map import assignee_candidate_ids_for_team

    sd = step_by_key(process_key)
    if not sd:
        raise PlanningError('Công đoạn không thuộc mẫu.')
    slug = (team_slug or '').strip().lower() or _team_slug_for_process_key(process_key)
    if not slug:
        raise PlanningError('Không xác định được tổ chuyền của công đoạn.')

    mo = SxProductionOrder.objects.select_for_update().get(pk=mo_id, is_demo=False)
    if mo.status in (SxProductionOrder.STATUS_DRAFT, SxProductionOrder.STATUS_CANCELLED):
        raise PlanningError('Lệnh sản xuất chưa phát hành hoặc đã hủy.')
    if is_team_job_closed(mo_id=mo.pk, team_slug=slug):
        raise PlanningError(
            'Tổ đã hoàn thành lệnh này — mở lại nếu cần phân công. Tổ sau không bị chặn.'
        )
    step = ensure_mo_step_for_template(mo=mo, step_def=sd)
    User = get_user_model()
    allowed = assignee_candidate_ids_for_team(slug, assigned_by) if assigned_by is not None else set()
    already = set(
        SxMoProcessAssignee.objects.filter(mo_process_step=step).values_list('user_id', flat=True),
    )
    keep: set[int] = set()
    for uid in user_ids:
        if not uid:
            continue
        uid = int(uid)
        if assigned_by is not None and uid not in allowed and uid not in already:
            raise PlanningError(
                'Nhân viên không thuộc phạm vi tổ/bộ phận đã map hoặc không phải cấp dưới của bạn.',
            )
        if not User.objects.filter(pk=uid, is_active=True).exists():
            continue
        keep.add(uid)
        SxMoProcessAssignee.objects.get_or_create(
            mo_process_step=step,
            user_id=uid,
            defaults={'assigned_by': assigned_by if getattr(assigned_by, 'is_authenticated', False) else None},
        )
    SxMoProcessAssignee.objects.filter(mo_process_step=step).exclude(user_id__in=keep).delete()
    return step


def _person_label(user) -> str:
    if not user:
        return ''
    p = getattr(user, 'profile', None)
    label = ((getattr(p, 'full_name', None) or '') if p else '').strip()
    return label or user.get_full_name() or user.username


def is_team_job_closed(*, mo_id: int, team_slug: str = '', process_name: str = '') -> bool:
    slug = (team_slug or '').strip().lower()
    if not slug and process_name:
        from san_xuat.services.progress_template import team_slug_for_process_label

        slug = team_slug_for_process_label(process_name) or ''
    if not slug or not mo_id:
        return False
    return SxTeamWorkClose.objects.filter(
        production_order_id=mo_id, team_slug=slug, is_demo=False,
    ).exists()


def team_job_closes(*, slug: str, mo_ids: list[int]) -> dict[int, SxTeamWorkClose]:
    if not mo_ids:
        return {}
    qs = (
        SxTeamWorkClose.objects.filter(
            team_slug=(slug or '').strip().lower(),
            production_order_id__in=mo_ids,
            is_demo=False,
        )
        .select_related('created_by', 'created_by__profile')
    )
    return {c.production_order_id: c for c in qs}


def attach_team_job_closes(jobs: list[TeamWorkJob], *, slug: str) -> list[TeamWorkJob]:
    closes = team_job_closes(slug=slug, mo_ids=[j.mo.pk for j in jobs])
    for job in jobs:
        rec = closes.get(job.mo.pk)
        job.closed = rec is not None
        job.closed_at = rec.closed_at if rec else None
        job.closed_by_label = _person_label(rec.created_by) if rec else ''
    return jobs


@transaction.atomic
def close_team_job(*, mo_id: int, team_slug: str, user=None, notes: str = '') -> SxTeamWorkClose:
    slug = (team_slug or '').strip().lower()
    if not team_by_slug(slug):
        raise PlanningError('Tổ không hợp lệ.')
    mo = SxProductionOrder.objects.select_for_update().get(pk=mo_id, is_demo=False)
    if mo.status in (SxProductionOrder.STATUS_DRAFT, SxProductionOrder.STATUS_CANCELLED):
        raise PlanningError('Lệnh sản xuất chưa phát hành hoặc đã hủy.')
    rec, created = SxTeamWorkClose.objects.get_or_create(
        production_order=mo,
        team_slug=slug,
        defaults={
            'notes': (notes or '').strip(),
            'created_by': user if getattr(user, 'is_authenticated', False) else None,
            'is_demo': False,
        },
    )
    if not created:
        raise PlanningError('Lệnh này tổ đã hoàn thành.')
    return rec


@transaction.atomic
def reopen_team_job(*, mo_id: int, team_slug: str) -> int:
    slug = (team_slug or '').strip().lower()
    if not team_by_slug(slug):
        raise PlanningError('Tổ không hợp lệ.')
    deleted, _ = SxTeamWorkClose.objects.filter(
        production_order_id=mo_id, team_slug=slug, is_demo=False,
    ).delete()
    if not deleted:
        raise PlanningError('Lệnh này tổ chưa hoàn thành.')
    return int(deleted)


def assignee_candidate_options(*, slug: str = '', assigner=None, limit: int = 300) -> list[dict]:
    """Danh sách NV gợi ý gán theo map bộ phận + phạm vi tổ trưởng."""
    from san_xuat.services.team_division_map import assignee_candidates_for_team

    if slug and assigner is not None:
        return assignee_candidates_for_team(slug, assigner, limit=limit)

    # Legacy fallback — tránh lộ toàn công ty khi thiếu slug/assigner
    return []
