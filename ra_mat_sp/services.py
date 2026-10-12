"""Nghiệp vụ kế hoạch ra mắt: mã, sinh checklist, dời ngày, % sẵn sàng, chuyển trạng thái."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from thiet_ke_sp.models import Status as DossierStatus

from .models import (
    CLOSED_TASK_STATUSES,
    GROUP_WEIGHTS,
    OPEN_TASK_STATUSES,
    PREPARING_STATUSES,
    REVIEW_OFFSETS,
    APPROVAL_STATUSES,
    AuditLog,
    ChecklistTemplateItem,
    Decision,
    DecisionKind,
    Importance,
    LaunchDecision,
    LaunchPlan,
    LaunchRisk,
    LaunchSequence,
    LaunchTask,
    PostLaunchReview,
    ReviewMilestone,
    RiskSeverity,
    Status,
    TaskGroup,
    TaskStatus,
)

PRODUCTION_STATE_LABELS = {
    'transferred': 'Đã chuyển SX',
    'pending': 'Chờ Thư viện chuyển SX',
    'design': 'Chưa bàn giao thiết kế',
}


def production_state(dossier) -> str:
    """transferred: đã có hồ sơ SX · pending: đã vào Thư viện, chờ chuyển · design: chưa bàn giao."""
    if dossier.status not in (DossierStatus.HANDED_OVER, DossierStatus.CLOSED):
        return 'design'
    handover = getattr(dossier, 'handover', None)
    if handover is None:
        return 'design'
    return 'transferred' if handover.is_transferred else 'pending'


class WorkflowError(Exception):
    pass


def display_name(user) -> str:
    if user is None:
        return ''
    profile = getattr(user, 'profile', None)
    name = (getattr(profile, 'full_name', '') or '').strip() if profile else ''
    return name or (user.get_full_name() or '').strip() or user.username


# ---------------------------------------------------------------------------
# Mã, nhật ký, trạng thái
# ---------------------------------------------------------------------------

def next_code(year: int | None = None) -> str:
    year = year or timezone.localdate().year
    with transaction.atomic():
        seq, _ = LaunchSequence.objects.select_for_update().get_or_create(year=year)
        seq.last_no = F('last_no') + 1
        seq.save(update_fields=['last_no'])
        seq.refresh_from_db()
        return f'LRM-{year}-{seq.last_no:04d}'


def log(plan: LaunchPlan, user, action: str, message: str, *, is_status: bool = False) -> None:
    AuditLog.objects.create(plan=plan, user=user, action=action, message=message, is_status=is_status)


def set_status(plan: LaunchPlan, status: str, user, message: str = '') -> None:
    old = plan.get_status_display()
    plan.status = status
    plan.status_changed_at = timezone.now()
    plan.save(update_fields=['status', 'status_changed_at', 'paused_from_status', 'launched_at', 'updated_at'])
    text = f'{old} → {plan.get_status_display()}'
    if message:
        text = f'{text}. {message}'
    log(plan, user, 'status', text, is_status=True)


# ---------------------------------------------------------------------------
# Sinh checklist, dời ngày
# ---------------------------------------------------------------------------

def plan_product_groups(plan: LaunchPlan) -> set[str]:
    return {g for g in plan.products.values_list('dossier__product_group', flat=True) if g}


def template_items_for(groups: set[str]):
    items = ChecklistTemplateItem.objects.filter(is_active=True)
    return [i for i in items if not i.product_group or i.product_group in groups]


def generate_tasks(plan: LaunchPlan) -> int:
    groups = plan_product_groups(plan)
    existing = set(plan.tasks.exclude(template_item=None).values_list('template_item_id', flat=True))
    tasks = [
        LaunchTask(
            plan=plan,
            template_item=item,
            group=item.group,
            offset_days=item.offset_days,
            title=item.title,
            deliverable=item.deliverable,
            importance=item.importance,
            is_go_blocker=item.is_go_blocker,
            owner_id=plan.coordinator_id,
            due_date=plan.launch_date + timedelta(days=item.offset_days),
            sort_order=item.sort_order,
        )
        for item in template_items_for(groups)
        if item.pk not in existing
    ]
    LaunchTask.objects.bulk_create(tasks)
    return len(tasks)


def ensure_reviews(plan: LaunchPlan) -> None:
    for milestone, offset in REVIEW_OFFSETS.items():
        PostLaunchReview.objects.get_or_create(
            plan=plan, milestone=milestone,
            defaults={'due_date': plan.launch_date + timedelta(days=offset)},
        )


def reschedule(plan: LaunchPlan) -> int:
    """Ngày ra mắt đổi → tính lại hạn các việc chưa xong (trừ điều kiện có hạn riêng) và ngày đánh giá."""
    changed = 0
    for task in plan.tasks.filter(status__in=OPEN_TASK_STATUSES, is_condition=False):
        new_due = plan.launch_date + timedelta(days=task.offset_days)
        if task.due_date != new_due:
            task.due_date = new_due
            task.save(update_fields=['due_date', 'updated_at'])
            changed += 1
    for review in plan.reviews.filter(submitted_at__isnull=True):
        review.due_date = plan.launch_date + timedelta(days=REVIEW_OFFSETS[review.milestone])
        review.save(update_fields=['due_date'])
    return changed


def sync_products(plan: LaunchPlan, dossiers) -> tuple[int, int]:
    from .models import LaunchPlanProduct

    wanted = {d.pk for d in dossiers}
    current = set(plan.products.values_list('dossier_id', flat=True))
    removed = current - wanted
    if removed:
        plan.products.filter(dossier_id__in=removed).delete()
    added = [d for d in dossiers if d.pk not in current]
    base = plan.products.count()
    LaunchPlanProduct.objects.bulk_create([
        LaunchPlanProduct(plan=plan, dossier=d, planned_qty=d.expected_qty, sort_order=base + i)
        for i, d in enumerate(added)
    ])
    return len(added), len(removed)


@transaction.atomic
def create_plan(plan: LaunchPlan, dossiers, user) -> LaunchPlan:
    plan.code = next_code(plan.launch_date.year if plan.launch_date else None)
    plan.created_by = user
    plan.status = Status.DRAFT
    plan.save()
    sync_products(plan, dossiers)
    count = generate_tasks(plan)
    ensure_reviews(plan)
    log(plan, user, 'create', f'Tạo kế hoạch, sinh {count} công việc từ checklist mẫu.', is_status=True)
    return plan


@transaction.atomic
def update_plan(plan: LaunchPlan, dossiers, user, *, old_launch_date: date) -> None:
    plan.save()
    added, removed = sync_products(plan, dossiers)
    parts = ['Cập nhật thông tin kế hoạch']
    if added or removed:
        parts.append(f'sản phẩm +{added}/-{removed}')
        generate_tasks(plan)
    if plan.launch_date != old_launch_date:
        moved = reschedule(plan)
        parts.append(
            f'dời ngày ra mắt {old_launch_date:%d/%m/%Y} → {plan.launch_date:%d/%m/%Y}, tính lại hạn {moved} việc'
        )
    log(plan, user, 'update', ', '.join(parts) + '.')
    refresh_risk(plan, user)


# ---------------------------------------------------------------------------
# % sẵn sàng, cảnh báo
# ---------------------------------------------------------------------------

@dataclass
class GroupReadiness:
    key: str
    label: str
    weight: int
    pct: int | None
    done: int
    total: int
    overdue: int


def readiness(plan: LaunchPlan, tasks=None) -> dict:
    tasks = list(plan.tasks.all()) if tasks is None else tasks
    today = timezone.localdate()
    groups = []
    score = 0.0
    weight_sum = 0
    for key, gw in GROUP_WEIGHTS.items():
        rows = [t for t in tasks if t.group == key and t.offset_days <= 0 and t.status != TaskStatus.NA]
        total_w = sum(t.weight for t in rows)
        done_w = sum(t.weight for t in rows if t.status == TaskStatus.DONE)
        pct = round(done_w * 100 / total_w) if total_w else None
        groups.append(GroupReadiness(
            key=key, label=TaskGroup(key).label, weight=gw, pct=pct,
            done=sum(1 for t in rows if t.status == TaskStatus.DONE), total=len(rows),
            overdue=sum(1 for t in rows if t.status in OPEN_TASK_STATUSES and t.due_date < today),
        ))
        if total_w:
            score += gw * done_w / total_w
            weight_sum += gw
    open_tasks = [t for t in tasks if t.status in OPEN_TASK_STATUSES]
    overdue = [t for t in open_tasks if t.due_date < today]
    return {
        'pct': round(score * 100 / weight_sum) if weight_sum else 0,
        'groups': groups,
        'open_blockers': [t for t in open_tasks if t.is_go_blocker],
        'overdue': overdue,
        'overdue_blockers': [t for t in overdue if t.is_go_blocker],
        'done': sum(1 for t in tasks if t.status in CLOSED_TASK_STATUSES),
        'total': len(tasks),
    }


def tone(plan: LaunchPlan, ready: dict, open_high_risks: int = 0) -> str:
    """Màu cảnh báo: green ổn · amber chậm · red rủi ro chặn · purple chờ quyết định · gray dừng/nháp."""
    if plan.status in (Status.DRAFT, Status.PAUSED, Status.CANCELLED):
        return 'gray'
    if plan.status in APPROVAL_STATUSES:
        return 'purple'
    if plan.status in (Status.LAUNCHED, Status.REVIEWING, Status.DONE, Status.READY):
        return 'green'
    if plan.status == Status.AT_RISK or ready['overdue_blockers']:
        return 'red'
    if ready['overdue'] or open_high_risks:
        return 'amber'
    return 'green'


TONE_LABELS = {
    'green': 'Đúng tiến độ',
    'amber': 'Có việc chậm',
    'red': 'Rủi ro chặn ra mắt',
    'purple': 'Chờ quyết định',
    'gray': 'Chưa chạy / dừng',
}


def is_risky(plan: LaunchPlan) -> bool:
    today = timezone.localdate()
    if plan.risks.filter(state=LaunchRisk.STATE_OPEN, severity=RiskSeverity.HIGH).exists():
        return True
    overdue = plan.tasks.filter(status__in=OPEN_TASK_STATUSES, due_date__lt=today, offset_days__lte=0)
    return overdue.filter(is_go_blocker=True).exists() or overdue.filter(importance=Importance.HIGH).exists()


def refresh_risk(plan: LaunchPlan, user=None) -> None:
    """Tự gán / gỡ trạng thái «Có rủi ro» khi đang chuẩn bị."""
    if plan.status not in PREPARING_STATUSES:
        return
    risky = is_risky(plan)
    if risky and plan.status == Status.PREPARING:
        set_status(plan, Status.AT_RISK, user, 'Tự động: có việc quan trọng trễ hạn hoặc rủi ro mức Cao.')
    elif not risky and plan.status == Status.AT_RISK:
        set_status(plan, Status.PREPARING, user, 'Tự động: đã xử lý các việc trễ / rủi ro mức Cao.')


def go_conditions(plan: LaunchPlan, tasks=None) -> list[dict]:
    tasks = list(plan.tasks.all()) if tasks is None else tasks
    rows = []
    links = list(plan.products.select_related('dossier__handover'))
    pending = [l.dossier for l in links if production_state(l.dossier) != 'transferred']
    rows.append({
        'label': 'Sản phẩm đã chuyển sản xuất',
        'ok': bool(links) and not pending,
        'note': ', '.join(f'{d.code} ({PRODUCTION_STATE_LABELS[production_state(d)]})' for d in pending)
        if pending else ('' if links else 'Chưa gắn sản phẩm'),
        'task': None,
    })
    for t in tasks:
        if t.is_go_blocker and not t.is_condition:
            rows.append({
                'label': t.title,
                'ok': t.status in CLOSED_TASK_STATUSES,
                'note': f'{t.milestone} · {t.get_status_display()}',
                'task': t,
            })
    high = plan.risks.filter(state=LaunchRisk.STATE_OPEN, severity=RiskSeverity.HIGH).count()
    rows.append({
        'label': 'Không còn rủi ro mức Cao đang mở',
        'ok': high == 0,
        'note': f'{high} rủi ro mức Cao' if high else '',
        'task': None,
    })
    return rows


# ---------------------------------------------------------------------------
# Công việc & rủi ro
# ---------------------------------------------------------------------------

def update_task(task: LaunchTask, user, *, status: str, evidence: str, delay_reason: str,
                owner=None, due_date: date | None = None, can_assign: bool = False) -> None:
    today = timezone.localdate()
    if status not in TaskStatus.values:
        raise WorkflowError('Trạng thái công việc không hợp lệ.')
    evidence = (evidence or '').strip()
    delay_reason = (delay_reason or '').strip()
    effective_due = due_date if (can_assign and due_date) else task.due_date
    if status == TaskStatus.BLOCKED and not delay_reason:
        raise WorkflowError('Ghi rõ vướng mắc khi chuyển công việc sang «Vướng mắc».')
    if status == TaskStatus.DONE:
        if task.is_go_blocker and not evidence:
            raise WorkflowError('Điều kiện Go/No-Go cần ghi bằng chứng / kết quả khi hoàn thành.')
        if effective_due < today and not delay_reason:
            raise WorkflowError('Công việc hoàn thành trễ hạn — nhập lý do trễ.')
    changes = []
    if task.status != status:
        changes.append(f'{task.get_status_display()} → {TaskStatus(status).label}')
        task.status = status
        if status == TaskStatus.DONE:
            task.completed_at = timezone.now()
            task.completed_by = user
        else:
            task.completed_at = None
            task.completed_by = None
    if can_assign:
        if owner is not None and owner.pk != task.owner_id:
            changes.append(f'giao cho {display_name(owner)}')
            task.owner = owner
        if due_date and due_date != task.due_date:
            changes.append(f'hạn {task.due_date:%d/%m} → {due_date:%d/%m}')
            task.due_date = due_date
    task.evidence = evidence
    task.delay_reason = delay_reason
    task.save()
    log(task.plan, user, 'task', f'Công việc «{task.title}»: ' + (', '.join(changes) if changes else 'cập nhật ghi chú') + '.')
    refresh_risk(task.plan, user)


def add_task(plan: LaunchPlan, user, *, group: str, title: str, due_date: date, owner, importance: str,
             is_go_blocker: bool, deliverable: str = '') -> LaunchTask:
    task = LaunchTask.objects.create(
        plan=plan, group=group, title=title.strip(), deliverable=(deliverable or '').strip(),
        offset_days=(due_date - plan.launch_date).days, due_date=due_date, owner=owner,
        importance=importance, is_go_blocker=is_go_blocker, sort_order=900,
    )
    log(plan, user, 'task_add', f'Thêm công việc «{task.title}» ({task.milestone}).')
    refresh_risk(plan, user)
    return task


def delete_task(task: LaunchTask, user) -> None:
    plan = task.plan
    title = task.title
    task.delete()
    log(plan, user, 'task_delete', f'Xóa công việc «{title}».')
    refresh_risk(plan, user)


def add_risk(plan: LaunchPlan, user, risk: LaunchRisk) -> None:
    risk.plan = plan
    risk.created_by = user
    risk.save()
    log(plan, user, 'risk', f'Ghi nhận rủi ro ({risk.get_severity_display()}): {risk.description[:120]}')
    refresh_risk(plan, user)


def resolve_risk(risk: LaunchRisk, user, resolution: str) -> None:
    resolution = (resolution or '').strip()
    if not resolution:
        raise WorkflowError('Nhập kết quả xử lý rủi ro.')
    risk.state = LaunchRisk.STATE_RESOLVED
    risk.resolution = resolution
    risk.resolved_at = timezone.now()
    risk.save(update_fields=['state', 'resolution', 'resolved_at'])
    log(risk.plan, user, 'risk', f'Đã xử lý rủi ro: {risk.description[:120]}')
    refresh_risk(risk.plan, user)


# ---------------------------------------------------------------------------
# Duyệt kế hoạch, Go/No-Go, ra mắt, đánh giá
# ---------------------------------------------------------------------------

def _require(text: str, message: str) -> str:
    text = (text or '').strip()
    if not text:
        raise WorkflowError(message)
    return text


def submit_plan(plan: LaunchPlan, user) -> None:
    if plan.status != Status.DRAFT:
        raise WorkflowError('Chỉ gửi duyệt kế hoạch ở trạng thái Nháp.')
    if not plan.approver_id:
        raise WorkflowError('Chọn Người duyệt trước khi gửi duyệt.')
    if not plan.products.exists():
        raise WorkflowError('Kế hoạch chưa có sản phẩm nào.')
    set_status(plan, Status.PLAN_PENDING, user, 'Gửi duyệt kế hoạch.')


def decide_plan(plan: LaunchPlan, user, decision: str, comment: str) -> None:
    if plan.status != Status.PLAN_PENDING:
        raise WorkflowError('Kế hoạch không ở trạng thái chờ duyệt.')
    if decision != Decision.APPROVED:
        comment = _require(comment, 'Nhập ý kiến khi yêu cầu chỉnh sửa hoặc hủy.')
    target = {
        Decision.APPROVED: Status.PREPARING,
        Decision.REQUEST_CHANGE: Status.DRAFT,
        Decision.CANCELLED: Status.CANCELLED,
    }.get(decision)
    if target is None:
        raise WorkflowError('Quyết định không hợp lệ.')
    LaunchDecision.objects.create(plan=plan, kind=DecisionKind.PLAN, decision=decision, comment=comment, decided_by=user)
    set_status(plan, target, user, f'{Decision(decision).label}{": " + comment if comment else ""}')
    refresh_risk(plan, user)


def submit_go(plan: LaunchPlan, user) -> None:
    if plan.status not in PREPARING_STATUSES:
        raise WorkflowError('Chỉ trình Go/No-Go khi kế hoạch đang chuẩn bị.')
    if not plan.approver_id:
        raise WorkflowError('Chọn Người duyệt trước khi trình Go/No-Go.')
    set_status(plan, Status.LAUNCH_PENDING, user, 'Trình họp Go/No-Go.')


@dataclass
class GoInput:
    decision: str
    comment: str = ''
    new_launch_date: date | None = None
    condition_text: str = ''
    condition_owner: object = None
    condition_due: date | None = None


@transaction.atomic
def decide_go(plan: LaunchPlan, user, data: GoInput) -> None:
    if plan.status != Status.LAUNCH_PENDING:
        raise WorkflowError('Kế hoạch không ở trạng thái chờ duyệt ra mắt.')
    if data.decision not in (Decision.GO, Decision.GO_CONDITIONAL, Decision.POSTPONE, Decision.PAUSED, Decision.CANCELLED):
        raise WorkflowError('Quyết định không hợp lệ.')
    comment = (data.comment or '').strip()
    if data.decision != Decision.GO:
        comment = _require(comment, 'Nhập ý kiến cho quyết định này.')
    tasks = list(plan.tasks.all())
    ready = readiness(plan, tasks)
    decision = LaunchDecision(
        plan=plan, kind=DecisionKind.GO, decision=data.decision, comment=comment,
        readiness=ready['pct'], decided_by=user,
    )
    if data.decision == Decision.GO:
        missing = [c['label'] for c in go_conditions(plan, tasks) if not c['ok']]
        if missing:
            raise WorkflowError(
                'Chưa đủ điều kiện bắt buộc: ' + '; '.join(missing[:4])
                + ('…' if len(missing) > 4 else '') + '. Dùng «Ra mắt có điều kiện» nếu vẫn ra mắt.'
            )
        decision.save()
        set_status(plan, Status.READY, user, 'Go: đủ điều kiện ra mắt.' + (f' {comment}' if comment else ''))
    elif data.decision == Decision.GO_CONDITIONAL:
        text = _require(data.condition_text, 'Nhập điều kiện phải hoàn thành.')
        if data.condition_owner is None:
            raise WorkflowError('Chọn người xử lý điều kiện.')
        if not data.condition_due:
            raise WorkflowError('Chọn hạn xử lý điều kiện.')
        decision.condition_text = text
        decision.condition_owner = data.condition_owner
        decision.condition_due = data.condition_due
        decision.save()
        LaunchTask.objects.create(
            plan=plan, group=TaskGroup.APPROVAL, title=text, deliverable='Điều kiện từ quyết định Go/No-Go',
            offset_days=(data.condition_due - plan.launch_date).days, due_date=data.condition_due,
            owner=data.condition_owner, importance=Importance.HIGH, is_condition=True, sort_order=950,
        )
        set_status(plan, Status.READY, user, f'Ra mắt có điều kiện: {text}. {comment}')
    elif data.decision == Decision.POSTPONE:
        if not data.new_launch_date or data.new_launch_date <= timezone.localdate():
            raise WorkflowError('Chọn ngày ra mắt mới sau hôm nay.')
        old = plan.launch_date
        decision.new_launch_date = data.new_launch_date
        decision.save()
        plan.launch_date = data.new_launch_date
        plan.save(update_fields=['launch_date', 'updated_at'])
        moved = reschedule(plan)
        set_status(
            plan, Status.PREPARING, user,
            f'Dời ngày ra mắt {old:%d/%m/%Y} → {plan.launch_date:%d/%m/%Y}, tính lại hạn {moved} việc. {comment}',
        )
        refresh_risk(plan, user)
    elif data.decision == Decision.PAUSED:
        decision.save()
        plan.paused_from_status = Status.PREPARING
        set_status(plan, Status.PAUSED, user, f'Tạm dừng: {comment}')
    else:
        decision.save()
        set_status(plan, Status.CANCELLED, user, f'Hủy: {comment}')


def mark_launched(plan: LaunchPlan, user) -> None:
    if plan.status != Status.READY:
        raise WorkflowError('Chỉ xác nhận ra mắt khi kế hoạch đủ điều kiện ra mắt.')
    pending = [l.dossier for l in plan.products.select_related('dossier__handover')
               if production_state(l.dossier) != 'transferred']
    if pending:
        raise WorkflowError('Chưa chuyển sản xuất: ' + ', '.join(
            f'{d.code} ({PRODUCTION_STATE_LABELS[production_state(d)]})' for d in pending) + '.')
    plan.launched_at = timezone.now()
    set_status(plan, Status.LAUNCHED, user, 'Xác nhận đã mở bán.')


def stop_plan(plan: LaunchPlan, user, decision: str, comment: str) -> None:
    comment = _require(comment, 'Nhập lý do.')
    if decision == Decision.PAUSED:
        if plan.status in (Status.PAUSED, Status.LAUNCHED, Status.REVIEWING, Status.DONE, Status.CANCELLED):
            raise WorkflowError('Không tạm dừng được kế hoạch ở trạng thái này.')
        plan.paused_from_status = plan.status
        target = Status.PAUSED
    elif decision == Decision.RESUMED:
        if plan.status != Status.PAUSED:
            raise WorkflowError('Kế hoạch không ở trạng thái tạm dừng.')
        target = plan.paused_from_status or Status.PREPARING
        if target in (Status.AT_RISK, Status.LAUNCH_PENDING, Status.READY):
            target = Status.PREPARING
        plan.paused_from_status = ''
    elif decision == Decision.CANCELLED:
        if plan.status in (Status.DONE, Status.CANCELLED):
            raise WorkflowError('Kế hoạch đã kết thúc.')
        target = Status.CANCELLED
    else:
        raise WorkflowError('Thao tác không hợp lệ.')
    LaunchDecision.objects.create(plan=plan, kind=DecisionKind.STOP, decision=decision, comment=comment, decided_by=user)
    set_status(plan, target, user, f'{Decision(decision).label}: {comment}')
    refresh_risk(plan, user)


def can_review(plan: LaunchPlan, review: PostLaunchReview) -> bool:
    return plan.status in (Status.LAUNCHED, Status.REVIEWING) and review.due_date <= timezone.localdate()


def submit_review(review: PostLaunchReview, user, cleaned: dict) -> None:
    plan = review.plan
    if plan.status not in (Status.LAUNCHED, Status.REVIEWING):
        raise WorkflowError('Chỉ đánh giá sau khi kế hoạch đã ra mắt.')
    if review.due_date > timezone.localdate():
        raise WorkflowError(f'Chưa đến ngày đánh giá {review.get_milestone_display()} ({review.due_date:%d/%m/%Y}).')
    if review.milestone == ReviewMilestone.D30 and not cleaned.get('decision'):
        raise WorkflowError('Đánh giá D+30 cần chọn quyết định tiếp theo.')
    for key, value in cleaned.items():
        setattr(review, key, value)
    first = review.submitted_at is None
    review.submitted_by = user
    review.submitted_at = timezone.now()
    review.save()
    log(plan, user, 'review', f'{"Ghi" if first else "Cập nhật"} đánh giá {review.get_milestone_display()}.')
    if review.milestone == ReviewMilestone.D30:
        set_status(plan, Status.DONE, user, f'Đánh giá D+30: {review.get_decision_display()}.')
    elif plan.status == Status.LAUNCHED:
        set_status(plan, Status.REVIEWING, user, f'Bắt đầu đánh giá sau ra mắt ({review.get_milestone_display()}).')
