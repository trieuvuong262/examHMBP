"""Công việc tổ — hàng đợi CD theo bộ phận (mẫu cố định)."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch

from san_xuat.hub_models import (
    SxMoProcessAssignee,
    SxMoProcessStep,
    SxProductionOrder,
)
from san_xuat.services.order_progress_sheet import ensure_progress_work_centers, work_center_map
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


@dataclass
class TeamWorkJob:
    mo: SxProductionOrder
    rows: list[TeamWorkRow]
    step_count: int = 0
    assigned_count: int = 0
    done_count: int = 0
    run_count: int = 0
    wait_count: int = 0


def group_team_work_jobs(rows: list[TeamWorkRow]) -> list[TeamWorkJob]:
    """Gom CD theo LSX — mỗi LSX là một việc."""
    jobs: list[TeamWorkJob] = []
    by_mo: dict[int, TeamWorkJob] = {}
    for row in rows:
        job = by_mo.get(row.mo.pk)
        if job is None:
            job = TeamWorkJob(mo=row.mo, rows=[])
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

    rows: list[TeamWorkRow] = []
    for mo in qs[:80]:
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
            rows.append(
                TeamWorkRow(
                    mo=mo,
                    step_def=sd,
                    mo_step=mo_step,
                    assignees=assignees,
                    status=status,
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


def assignee_candidate_options(*, slug: str = '', assigner=None, limit: int = 300) -> list[dict]:
    """Danh sách NV gợi ý gán theo map bộ phận + phạm vi tổ trưởng."""
    from san_xuat.services.team_division_map import assignee_candidates_for_team

    if slug and assigner is not None:
        return assignee_candidates_for_team(slug, assigner, limit=limit)

    # Legacy fallback — tránh lộ toàn công ty khi thiếu slug/assigner
    return []
