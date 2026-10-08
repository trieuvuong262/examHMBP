"""Số liệu màn Tổng quan (mục 12 tài liệu nghiệp vụ)."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q
from django.utils import timezone

from thiet_ke_sp import permissions as perms
from thiet_ke_sp.models import (
    DONE_STATUSES,
    IN_PROGRESS_STATUSES,
    STATUS_BADGES,
    STATUS_TONES,
    Approval,
    ApprovalDecision,
    ApprovalStage,
    Criterion,
    EvaluationItem,
    ProductDevelopment,
    ProductGroup,
    Status,
    Task,
)


MONTHLY_SPAN = 6


def _month_start(today):
    return today.replace(day=1)


def live_dossiers():
    """Hồ sơ thật — dữ liệu demo không tính vào số liệu tổng quan / báo cáo."""
    return ProductDevelopment.objects.filter(is_demo=False)


def _shift_month(month_start, delta: int):
    index = month_start.year * 12 + month_start.month - 1 + delta
    return month_start.replace(year=index // 12, month=index % 12 + 1, day=1)


def monthly_rows(qs, today, months: int = MONTHLY_SPAN) -> list[dict]:
    """Số đề xuất / duyệt sản xuất / hủy theo từng tháng, cũ → mới."""
    current = _month_start(today)
    first = _shift_month(current, -(months - 1))
    starts = [_shift_month(first, i) for i in range(months)]

    def per_month(field: str, **extra) -> Counter:
        values = qs.filter(**{f'{field}__date__gte': first}, **extra).values_list(field, flat=True)
        return Counter(timezone.localtime(v).date().replace(day=1) for v in values if v is not None)

    proposed = per_month('created_at')
    approved = per_month('approved_at')
    cancelled = per_month('closed_at', status=Status.CANCELLED)
    peak = max([proposed[s] for s in starts] + [approved[s] for s in starts] + [cancelled[s] for s in starts] + [1])
    return [
        {
            'label': s.strftime('%m/%Y'),
            'proposed': proposed[s], 'approved': approved[s], 'cancelled': cancelled[s],
            'w_proposed': round(proposed[s] * 100 / peak), 'w_approved': round(approved[s] * 100 / peak),
            'w_cancelled': round(cancelled[s] * 100 / peak),
        }
        for s in starts
    ]


def _avg(values) -> Decimal | None:
    values = [Decimal(v) for v in values if v is not None]
    if not values:
        return None
    return (sum(values) / len(values)).quantize(Decimal('0.1'))


def dashboard_data() -> dict:
    now = timezone.now()
    today = timezone.localdate()
    month_start = _month_start(today)
    qs = live_dossiers()

    counts = dict(qs.values_list('status').annotate(n=Count('pk')).values_list('status', 'n'))
    status_rows = [
        {'value': s.value, 'label': s.label, 'count': counts.get(s.value, 0), 'badge': STATUS_BADGES.get(s, 'secondary')}
        for s in Status
    ]

    live = qs.exclude(status__in=(Status.PAUSED, Status.CANCELLED, Status.CLOSED))
    open_tasks = Task.objects.filter(state=Task.STATE_OPEN, dossier__in=live).select_related(
        'dossier', 'assignee__profile',
    )
    overdue = [t for t in open_tasks.filter(due_at__lt=now).order_by('due_at')]
    due_soon = list(open_tasks.filter(due_at__gte=now, due_at__lt=now + timedelta(days=2)).order_by('due_at'))

    overdue_by_step = Counter(Status(t.step).label for t in overdue)
    overdue_by_user = Counter(perms.display_name(t.assignee) or '— Chưa giao —' for t in overdue)

    approved = list(qs.filter(approved_at__isnull=False).only('created_at', 'approved_at'))
    avg_days = _avg([(d.approved_at - d.created_at).days for d in approved])

    with_final = list(
        qs.filter(final_sample_version__isnull=False).select_related('final_sample_version')
    )
    first_pass = sum(1 for d in with_final if d.final_sample_version.version_no == 1)
    first_pass_rate = (Decimal(first_pass * 100) / len(with_final)).quantize(Decimal('0.1')) if with_final else None

    design_rounds = _design_rounds(qs)
    sample_rounds = qs.filter(sample_versions__isnull=False).annotate(
        rounds=Max('sample_versions__version_no'),
    ).values_list('rounds', flat=True)

    variance_rows = []
    for d in qs.filter(target_cost__isnull=False).exclude(status=Status.CANCELLED).order_by('-updated_at')[:200]:
        pct = d.cost_variance_pct
        if pct is not None:
            variance_rows.append(d)
    variance_rows.sort(key=lambda d: abs(d.cost_variance_pct), reverse=True)

    return {
        'status_rows': status_rows,
        'total': sum(counts.values()),
        'in_progress': sum(counts.get(s, 0) for s in IN_PROGRESS_STATUSES),
        'waiting_approval': sum(counts.get(s, 0) for s in (
            Status.BRIEF_PENDING, Status.DESIGN_PENDING, Status.MASTER_PENDING)),
        'done': sum(counts.get(s, 0) for s in DONE_STATUSES),
        'overdue_tasks': overdue[:30],
        'overdue_count': len(overdue),
        'due_soon_tasks': due_soon[:30],
        'overdue_by_step': overdue_by_step.most_common(),
        'overdue_by_user': overdue_by_user.most_common(10),
        'month_proposed': qs.filter(created_at__date__gte=month_start).count(),
        'month_approved': qs.filter(approved_at__date__gte=month_start).count(),
        'month_cancelled': qs.filter(status=Status.CANCELLED, closed_at__date__gte=month_start).count(),
        'monthly': monthly_rows(qs, today),
        'avg_dev_days': avg_days,
        'first_pass_rate': first_pass_rate,
        'first_pass_base': len(with_final),
        'avg_design_rounds': _avg(design_rounds),
        'avg_sample_rounds': _avg(sample_rounds),
        'avg_cost_variance_pct': _avg([d.cost_variance_pct for d in variance_rows]),
        'variance_rows': variance_rows[:10],
    }


def _design_rounds(qs):
    """Số lần trình duyệt thiết kế đến khi được duyệt (đếm quyết định duyệt thiết kế, không phụ thuộc số phương án)."""
    return qs.filter(approved_design_version__isnull=False).annotate(
        rounds=Count('approvals', filter=Q(approvals__stage=ApprovalStage.DESIGN)),
    ).values_list('rounds', flat=True)


def _pct(part: int, whole: int) -> Decimal | None:
    if not whole:
        return None
    return (Decimal(part * 100) / whole).quantize(Decimal('0.1'))


def _meters(pairs: list[tuple[str, int]]) -> list[dict]:
    total = sum(n for _label, n in pairs)
    peak = max((n for _label, n in pairs), default=0) or 1
    return [
        {'label': label, 'count': n, 'pct': _pct(n, total), 'width': round(n * 100 / peak)}
        for label, n in pairs
    ]


def report_data(*, collection: str = '', group: str = '') -> dict:
    now = timezone.now()
    today = timezone.localdate()
    month_start = _month_start(today)
    qs = live_dossiers()
    if collection:
        qs = qs.filter(collection=collection)
    if group:
        qs = qs.filter(product_group=group)

    counts = dict(qs.values_list('status').annotate(n=Count('pk')).values_list('status', 'n'))
    status_rows = [
        {'value': s.value, 'label': s.label, 'count': counts.get(s.value, 0), 'tone': STATUS_TONES.get(s, 'gray')}
        for s in Status if counts.get(s.value)
    ]

    approved = list(qs.filter(approved_at__isnull=False).only('created_at', 'approved_at'))
    design_rounds = _design_rounds(qs)
    sample_rounds = qs.filter(final_sample_version__isnull=False).annotate(
        rounds=Max('sample_versions__version_no'),
    ).values_list('rounds', flat=True)

    main_done = Task.objects.filter(
        dossier__in=qs, is_main=True, receipt__isnull=True, condition__isnull=True,
        state=Task.STATE_DONE, due_at__isnull=False, completed_at__isnull=False,
    ).only('due_at', 'completed_at')
    done_list = list(main_done)
    on_time = sum(1 for t in done_list if t.completed_at <= t.due_at)

    with_final = list(qs.filter(final_sample_version__isnull=False).select_related('final_sample_version').only(
        'product_group', 'final_sample_version__version_no',
    ))
    by_group = {}
    for d in with_final:
        row = by_group.setdefault(d.product_group, {'total': 0, 'first': 0, 'rounds': []})
        row['total'] += 1
        row['first'] += 1 if d.final_sample_version.version_no == 1 else 0
        row['rounds'].append(d.final_sample_version.version_no)
    group_labels = dict(ProductGroup.choices)
    first_pass_by_group = sorted(
        (
            {
                'label': group_labels.get(key, key), 'total': row['total'],
                'rate': _pct(row['first'], row['total']), 'avg_rounds': _avg(row['rounds']),
            }
            for key, row in by_group.items()
        ),
        key=lambda r: -r['total'],
    )

    criterion_labels = dict(Criterion.choices)
    fails = Counter(dict(
        EvaluationItem.objects.filter(
            evaluation__sample_version__dossier__in=qs, result=EvaluationItem.RESULT_FAIL,
        ).values_list('criterion').annotate(n=Count('pk')).values_list('criterion', 'n')
    ))
    reasons = [(criterion_labels.get(k, k), n) for k, n in fails.most_common()]
    design_changes = Approval.objects.filter(
        dossier__in=qs, stage=ApprovalStage.DESIGN, decision=ApprovalDecision.REQUEST_CHANGE,
    ).count()
    if design_changes:
        reasons.append(('Chỉnh thiết kế khi duyệt', design_changes))
    reasons.sort(key=lambda r: -r[1])

    live = qs.exclude(status__in=(Status.PAUSED, Status.CANCELLED, Status.CLOSED))
    overdue = list(Task.objects.filter(state=Task.STATE_OPEN, dossier__in=live, due_at__lt=now).select_related(
        'assignee__profile', 'dossier',
    ).order_by('due_at', 'pk'))
    overdue_by_step = Counter(Status(t.step).label for t in overdue)
    overdue_by_user = Counter(perms.display_name(t.assignee) or '— Chưa giao —' for t in overdue)

    variance_rows = [
        d for d in qs.filter(target_cost__isnull=False).exclude(status=Status.CANCELLED).order_by('-updated_at')[:200]
        if d.cost_variance_pct is not None
    ]
    variance_rows.sort(key=lambda d: abs(d.cost_variance_pct), reverse=True)

    return {
        'total': sum(counts.values()),
        'status_rows': status_rows,
        'avg_dev_days': _avg([(d.approved_at - d.created_at).days for d in approved]),
        'approved_base': len(approved),
        'avg_design_rounds': _avg(design_rounds),
        'avg_sample_rounds': _avg(sample_rounds),
        'on_time_rate': _pct(on_time, len(done_list)),
        'on_time_base': len(done_list),
        'first_pass_rate': _pct(sum(r['first'] for r in by_group.values()), len(with_final)),
        'first_pass_base': len(with_final),
        'first_pass_by_group': first_pass_by_group,
        'revision_reasons': _meters(reasons),
        'overdue_count': len(overdue),
        'overdue_tasks': overdue[:50],
        'overdue_by_step': _meters(overdue_by_step.most_common()),
        'overdue_by_user': _meters(overdue_by_user.most_common(10)),
        'month_proposed': qs.filter(created_at__date__gte=month_start).count(),
        'month_approved': qs.filter(approved_at__date__gte=month_start).count(),
        'month_cancelled': qs.filter(status=Status.CANCELLED, closed_at__date__gte=month_start).count(),
        'avg_cost_variance_pct': _avg([d.cost_variance_pct for d in variance_rows]),
        'variance_rows': variance_rows[:10],
    }
