"""Công việc tổ — hàng đợi CD theo bộ phận (mẫu cố định)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from san_xuat.hub_models import (
    SxMoProcessAssignee,
    SxMoProcessStep,
    SxProductionOrder,
    SxProductionOrderLine,
    SxProductionStat,
    SxSalesOrder,
    SxSubcontractOrder,
    SxTeamWorkAccept,
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
    step_by_label,
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
    accepted: bool = False
    priority: str = ''
    priority_label: str = ''
    due: object | None = None
    days_to_due: int | None = None
    is_overdue: bool = False
    qc_status: str = ''
    qc_required: bool = False
    qc_status_label: str = ''
    subcontract: object | None = None


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


def _step_defs_for_mo_team(
    *,
    slug: str,
    source_lines,
    fallback: list[ProgressStepDef],
) -> list[ProgressStepDef]:
    """CD phân công = CĐ trên Ob/Bom của đúng tổ; không lấy hết catalog 6 tổ."""
    from san_xuat.services.qc import resolve_team_slug_from_routing_line

    wanted: list[ProgressStepDef] = []
    seen: set[str] = set()
    for line in source_lines or []:
        if resolve_team_slug_from_routing_line(line) != slug:
            continue
        name = (
            getattr(line, 'op_name_vi', None)
            or getattr(line, 'process_name', None)
            or ''
        )
        sd = step_by_label(name)
        if sd is None or sd.key in seen:
            continue
        seen.add(sd.key)
        wanted.append(sd)
    return wanted or list(fallback)


def build_team_work_rows(*, slug: str, search: str = '') -> tuple[dict, list[TeamWorkRow]]:
    team = team_by_slug(slug)
    if not team:
        raise PlanningError('Tổ không hợp lệ.')
    ensure_progress_work_centers()
    step_defs = steps_for_group(team['group_key'])

    qs = (
        SxProductionOrder.objects.filter(is_demo=False)
        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .exclude(status=SxProductionOrder.STATUS_DRAFT)
        .select_related('sales_order', 'bom_version', 'routing')
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
            'sales_order__lines__routing_lines__work_center',
            'routing__lines__work_center',
            'bom_version__process_steps__work_center',
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
    from san_xuat.services.qc import ob_qc_teams, ob_source_lines

    rows: list[TeamWorkRow] = []
    for mo in mos:
        participating = {t.slug for t in ob_qc_teams(mo=mo)}
        if slug not in participating:
            continue
        mo_step_defs = _step_defs_for_mo_team(
            slug=slug,
            source_lines=ob_source_lines(mo=mo),
            fallback=step_defs,
        )
        sizes = _size_plans(mo)
        mo_stats = stats_by_mo.get(mo.pk, [])
        by_name: dict[str, SxMoProcessStep] = {}
        mo_label_set = {(s.label or '').strip().casefold() for s in mo_step_defs}
        for st in mo.mo_process_steps.all():
            key = (st.process_name or '').strip().casefold()
            if key in mo_label_set and key not in by_name:
                by_name[key] = st

        for sd in mo_step_defs:
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
    if active_subcontract_for_team(mo_id=mo.pk, team_slug=slug):
        raise PlanningError(
            'Tổ này đang thuê gia công — không phân công nội bộ. Nhận hàng trên phiếu GC.'
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


def active_subcontract_for_team(*, mo_id: int, team_slug: str):
    """Phiếu GC còn hiệu lực cho (lệnh, tổ) — không phân công / tiến độ nội bộ."""
    slug = (team_slug or '').strip().lower()
    if not mo_id or not slug:
        return None
    return (
        SxSubcontractOrder.objects.filter(
            production_order_id=mo_id,
            team_slug=slug,
            is_demo=False,
        )
        .exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
        .order_by('-order_date', '-pk')
        .first()
    )


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


def is_production_accepted(mo: SxProductionOrder) -> bool:
    """Đã nhận SX (LSX đang làm / xong) — mới mở Tiến độ / Hoàn thành tổ."""
    return mo.status in (
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    )


def _record_team_accept(*, mo: SxProductionOrder, team_slug: str, user=None) -> SxTeamWorkAccept | None:
    slug = (team_slug or '').strip().lower()
    if not slug or not team_by_slug(slug):
        return None
    rec, _created = SxTeamWorkAccept.objects.get_or_create(
        production_order=mo,
        team_slug=slug,
        defaults={
            'created_by': user if getattr(user, 'is_authenticated', False) else None,
            'is_demo': False,
        },
    )
    return rec


@transaction.atomic
def accept_production(*, mo_id: int, team_slug: str = '', user=None) -> SxProductionOrder:
    """Tổ bất kỳ nhận phiếu → LSX + ĐĐH (KHSX) sang Đang SX; ghi tổ đã nhận."""
    slug = (team_slug or '').strip().lower()
    if slug and not team_by_slug(slug):
        raise PlanningError('Tổ không hợp lệ.')
    mo = SxProductionOrder.objects.select_for_update().get(pk=mo_id, is_demo=False)
    # Không select_related('sales_order') cùng FOR UPDATE — Postgres cấm outer join nullable.
    if mo.sales_order_id:
        mo.sales_order  # lazy load trong transaction
    if mo.status in (SxProductionOrder.STATUS_DRAFT, SxProductionOrder.STATUS_CANCELLED):
        raise PlanningError('Lệnh sản xuất chưa phát hành hoặc đã hủy.')
    if mo.status == SxProductionOrder.STATUS_DONE:
        _record_team_accept(mo=mo, team_slug=slug, user=user)
        return mo
    if mo.status == SxProductionOrder.STATUS_RELEASED:
        mo.status = SxProductionOrder.STATUS_IN_PROGRESS
        mo.save(update_fields=['status'])
        if mo.sales_order_id:
            from san_xuat.services.plan_board import sync_plan_status

            sync_plan_status(mo.sales_order)
    elif mo.status != SxProductionOrder.STATUS_IN_PROGRESS:
        raise PlanningError('Lệnh không ở trạng thái chờ nhận sản xuất.')
    _record_team_accept(mo=mo, team_slug=slug, user=user)
    return mo


def ensure_team_accept(*, mo_id: int, team_slug: str, user=None) -> None:
    """Ghi tổ đã nhận khi vào tiến độ (LSX đã đang SX)."""
    mo = SxProductionOrder.objects.filter(pk=mo_id, is_demo=False).first()
    if not mo or not is_production_accepted(mo):
        return
    _record_team_accept(mo=mo, team_slug=team_slug, user=user)


def attach_team_job_closes(jobs: list[TeamWorkJob], *, slug: str) -> list[TeamWorkJob]:
    from san_xuat.services.goods_progress import PRIORITY_LABEL, PRIORITY_RANK

    closes = team_job_closes(slug=slug, mo_ids=[j.mo.pk for j in jobs])
    today = timezone.localdate()
    for job in jobs:
        job.accepted = is_production_accepted(job.mo)
        rec = closes.get(job.mo.pk)
        job.closed = rec is not None
        job.closed_at = rec.closed_at if rec else None
        job.closed_by_label = _person_label(rec.created_by) if rec else ''
        so = job.mo.sales_order if job.mo.sales_order_id else None
        priority = (so.plan_priority if so else '') or SxSalesOrder.PRIORITY_NORMAL
        if priority not in PRIORITY_RANK:
            priority = SxSalesOrder.PRIORITY_NORMAL
        due = (so.due_date if so else None) or job.mo.due_date or job.mo.planned_end
        days = (due - today).days if due else None
        job.priority = priority
        job.priority_label = PRIORITY_LABEL.get(priority, 'Thường')
        job.due = due
        job.days_to_due = days
        job.is_overdue = bool(
            due and days is not None and days < 0
            and job.mo.status != SxProductionOrder.STATUS_DONE
        )
    from san_xuat.services.qc import (
        QC_STATUS_LABELS,
        QC_STATUS_SKIP,
        ob_qc_teams,
        qc_status_map_for_mos,
    )

    status_map = qc_status_map_for_mos([j.mo for j in jobs])
    for job in jobs:
        required = {t.slug for t in ob_qc_teams(mo=job.mo)}
        job.qc_required = slug in required
        if job.qc_required:
            job.qc_status = status_map.get((job.mo.pk, slug), 'idle')
        else:
            job.qc_status = QC_STATUS_SKIP
        job.qc_status_label = QC_STATUS_LABELS.get(job.qc_status, job.qc_status)
    if jobs:
        latest: dict[int, SxSubcontractOrder] = {}
        qs = (
            SxSubcontractOrder.objects.filter(
                is_demo=False,
                production_order_id__in=[j.mo.pk for j in jobs],
                team_slug=slug,
            )
            .exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
            .order_by('-order_date', '-pk')
        )
        for row in qs:
            if row.production_order_id not in latest:
                latest[row.production_order_id] = row
        for job in jobs:
            job.subcontract = latest.get(job.mo.pk)
    jobs.sort(
        key=lambda j: (
            0 if j.is_overdue else 1,
            PRIORITY_RANK.get(j.priority, 3),
            j.due or date(9999, 12, 31),
            j.mo.code or '',
        )
    )
    return jobs


@transaction.atomic
def close_team_job(*, mo_id: int, team_slug: str, user=None, notes: str = '', require_accept: bool = True) -> SxTeamWorkClose:
    slug = (team_slug or '').strip().lower()
    if not team_by_slug(slug):
        raise PlanningError('Tổ không hợp lệ.')
    mo = SxProductionOrder.objects.select_for_update().get(pk=mo_id, is_demo=False)
    if mo.status in (SxProductionOrder.STATUS_DRAFT, SxProductionOrder.STATUS_CANCELLED):
        raise PlanningError('Lệnh sản xuất chưa phát hành hoặc đã hủy.')
    if require_accept and not is_production_accepted(mo):
        raise PlanningError('Cần nhận sản xuất trước khi hoàn thành.')
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
