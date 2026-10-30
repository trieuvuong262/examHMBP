"""Nghiệp vụ kế hoạch ra mắt: mã, sinh checklist, dời ngày, % sẵn sàng, chuyển trạng thái."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from thiet_ke_sp.models import Status as DossierStatus

from .models import (
    CLOSED_TASK_STATUSES,
    GROUP_PAGES,
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
    LaunchGroupDefault,
    LaunchPlan,
    LaunchPlanGroupOwner,
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
    handover = getattr(dossier, 'handover', None)
    if handover is not None and handover.is_transferred:
        return 'transferred'
    if handover is not None and dossier.status in (
        DossierStatus.HANDED_OVER, DossierStatus.CLOSED, DossierStatus.LIBRARY_REOPEN,
    ):
        return 'pending'
    return 'design'


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


def owner_ids_by_group(qs) -> dict[str, list[int]]:
    """{nhóm: [user_id, ...]} từ queryset LaunchGroupDefault / LaunchPlanGroupOwner (M2M `owners`)."""
    out: dict[str, list[int]] = {}
    for group, uid in qs.values_list('group', 'owners'):
        ids = out.setdefault(group, [])
        if uid is not None and uid not in ids:
            ids.append(uid)
    return out


def ensure_group_owners(plan: LaunchPlan) -> None:
    """Tạo dòng phụ trách nhóm còn thiếu: mặc định trong Thiết lập, không có thì người điều phối."""
    defaults = owner_ids_by_group(LaunchGroupDefault.objects.all())
    existing = set(plan.group_owners.values_list('group', flat=True))
    rows = [
        LaunchPlanGroupOwner(plan=plan, group=group)
        for group in TaskGroup.values
        if group not in existing
    ]
    if rows:
        LaunchPlanGroupOwner.objects.bulk_create(rows)
        for row in rows:
            default_ids = defaults.get(row.group, [])
            if default_ids:
                row.owners.set(default_ids)
            elif plan.coordinator_id:
                row.owners.add(plan.coordinator_id)


def group_owner_map(plan: LaunchPlan) -> dict[str, list[int]]:
    ensure_group_owners(plan)
    out = {}
    for row in plan.group_owners.all():
        ids = list(row.owners.values_list('pk', flat=True))
        out[row.group] = ids if ids else [plan.coordinator_id]
    return out


def milestone_starts(plan: LaunchPlan, offsets) -> dict[int, date]:
    """Ngày bắt đầu mặc định: việc mốc T-60 bắt đầu từ mốc T-90 liền trước; mốc đầu tiên bắt đầu từ ngày lập kế hoạch."""
    created = timezone.localdate(plan.created_at) if plan.created_at else timezone.localdate()
    starts: dict[int, date] = {}
    prev = None
    for offset in sorted(set(offsets)):
        due = plan.launch_date + timedelta(days=offset)
        start = plan.launch_date + timedelta(days=prev) if prev is not None else min(created, due)
        starts[offset] = min(start, due)
        prev = offset
    return starts


def generate_tasks(plan: LaunchPlan) -> int:
    ensure_group_owners(plan)
    groups = plan_product_groups(plan)
    existing = set(plan.tasks.exclude(template_item=None).values_list('template_item_id', flat=True))
    owners = group_owner_map(plan)
    items = template_items_for(groups)
    starts = milestone_starts(plan, [i.offset_days for i in items])
    tasks = []
    for item in items:
        if item.pk in existing:
            continue
        owner_ids = owners.get(item.group, [plan.coordinator_id])
        tasks.append(LaunchTask(
            plan=plan, template_item=item, group=item.group, offset_days=item.offset_days,
            title=item.title, deliverable=item.deliverable, importance=item.importance,
            is_go_blocker=item.is_go_blocker, owner_id=owner_ids[0],
            start_date=starts.get(item.offset_days),
            due_date=plan.launch_date + timedelta(days=item.offset_days), sort_order=item.sort_order,
        ))
    LaunchTask.objects.bulk_create(tasks)
    return len(tasks)


def prune_retired_tasks(plan: LaunchPlan) -> int:
    """Gỡ việc mẫu đã ngừng, còn trạng thái chưa làm và chưa có ghi chú. Giữ việc đã làm."""
    qs = plan.tasks.filter(
        template_item__is_active=False,
        status=TaskStatus.TODO,
        evidence='',
        delay_reason='',
        is_condition=False,
    )
    count = qs.count()
    qs.delete()
    return count


CHECKLIST_SYNC_STATUSES = (Status.DRAFT, Status.PLAN_PENDING, Status.PREPARING, Status.AT_RISK)


def sync_checklist_to_open_plans() -> int:
    added = 0
    for plan in LaunchPlan.objects.filter(status__in=CHECKLIST_SYNC_STATUSES):
        ensure_group_owners(plan)
        added += generate_tasks(plan)
        prune_retired_tasks(plan)
    return added


def parse_owner_map(post) -> dict:
    from thiet_ke_sp.forms import active_users

    users = {u.pk: u for u in active_users()}
    mapping = {}
    for key, _label in TaskGroup.choices:
        raw = post.getlist(f'owner_{key}')
        if not raw or (len(raw) == 1 and not raw[0]):
            mapping[key] = []
            continue
        ids = []
        for r in raw:
            if not r.isdigit() or int(r) not in users:
                raise WorkflowError(f'Người phụ trách nhóm «{_label}» không hợp lệ.')
            ids.append(int(r))
        mapping[key] = ids
    return mapping


def save_group_defaults(mapping: dict) -> None:
    for group, owner_ids in mapping.items():
        row, _ = LaunchGroupDefault.objects.get_or_create(group=group)
        row.owners.set(owner_ids)


def assign_group_owners(plan: LaunchPlan, user, mapping: dict) -> None:
    ensure_group_owners(plan)
    changed = []
    for row in plan.group_owners.all():
        new_ids = mapping.get(row.group) or []
        old_ids = set(row.owners.values_list('pk', flat=True))
        new_set = set(new_ids)
        if old_ids == new_set:
            continue
        row.owners.set(new_ids)
        changed.append(TaskGroup(row.group).label)
    if changed:
        log(plan, user, 'owners', 'Cập nhật người phụ trách nhóm: ' + ', '.join(changed) + '.')


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
            if task.start_date:
                task.start_date = task.start_date + (new_due - task.due_date)
            task.due_date = new_due
            task.save(update_fields=['start_date', 'due_date', 'updated_at'])
            changed += 1
    for review in plan.reviews.filter(submitted_at__isnull=True):
        review.due_date = plan.launch_date + timedelta(days=REVIEW_OFFSETS[review.milestone])
        review.save(update_fields=['due_date'])
    return changed


def library_styles(current_ids=()):
    """Style đang hiện trong Thư viện sản phẩm (đã bàn giao từ hồ sơ thiết kế), cộng style đã gắn sẵn."""
    from kho_san_pham.catalog_models import ProductStyle
    from kho_san_pham.choices import STYLE_SOURCE_DESIGN
    from thiet_ke_sp.models import Handover

    shelf = Handover.objects.filter(
        dossier__status__in=(DossierStatus.HANDED_OVER, DossierStatus.CLOSED),
    ).values('product_code')
    return ProductStyle.objects.filter(
        Q(pk__in=list(current_ids)) | Q(source=STYLE_SOURCE_DESIGN, is_active=True, code__in=shelf),
    ).select_related('product_type').order_by('code')


def dossiers_for_styles(styles) -> dict[int, object]:
    """Style → hồ sơ thiết kế nguồn (qua biên bản bàn giao / mã chính thức)."""
    from thiet_ke_sp.models import Handover, ProductDevelopment

    codes = {s.code.upper(): s.pk for s in styles}
    out: dict[int, object] = {}
    for h in Handover.objects.filter(product_code__in=list(codes)).select_related('dossier'):
        pk = codes.get((h.product_code or '').strip().upper())
        if pk:
            out.setdefault(pk, h.dossier)
    missing = [code for code, pk in codes.items() if pk not in out]
    if missing:
        q = Q()
        for code in missing:
            q |= Q(official_product_code__iexact=code)
        for d in ProductDevelopment.objects.filter(q).order_by('-created_at'):
            pk = codes.get((d.official_product_code or '').strip().upper())
            if pk:
                out.setdefault(pk, d)
    return out


def sync_products(plan: LaunchPlan, styles) -> tuple[int, int]:
    from .models import LaunchPlanProduct

    styles = list(styles)
    dossiers = dossiers_for_styles(styles)
    orphan = [s.code for s in styles if s.pk not in dossiers]
    if orphan:
        raise WorkflowError('Không tìm thấy hồ sơ thiết kế nguồn cho style: ' + ', '.join(orphan) + '.')
    wanted = {s.pk for s in styles}
    current = set(plan.products.values_list('style_id', flat=True))
    removed = current - wanted
    if removed:
        plan.products.filter(style_id__in=removed).delete()
    added = [s for s in styles if s.pk not in current]
    taken = set(plan.products.values_list('dossier_id', flat=True))
    dup = [s.code for s in added if dossiers[s.pk].pk in taken]
    if dup:
        raise WorkflowError('Style trùng hồ sơ thiết kế đã có trong kế hoạch: ' + ', '.join(dup) + '.')
    base = plan.products.count()
    LaunchPlanProduct.objects.bulk_create([
        LaunchPlanProduct(plan=plan, style=s, dossier=dossiers[s.pk], planned_qty=dossiers[s.pk].expected_qty,
                          sort_order=base + i)
        for i, s in enumerate(added)
    ])
    return len(added), len(removed)


@transaction.atomic
def create_plan(plan: LaunchPlan, styles, user) -> LaunchPlan:
    plan.code = next_code(plan.launch_date.year if plan.launch_date else None)
    plan.created_by = user
    plan.status = Status.DRAFT
    plan.save()
    sync_products(plan, styles)
    count = generate_tasks(plan)
    ensure_reviews(plan)
    log(plan, user, 'create', f'Tạo kế hoạch, sinh {count} công việc từ checklist mẫu.', is_status=True)
    return plan


@transaction.atomic
def update_plan(plan: LaunchPlan, styles, user, *, old_launch_date: date) -> None:
    plan.save()
    added, removed = sync_products(plan, styles)
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
    tab: str = 'timeline'


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
            tab=GROUP_PAGES.get(key, 'timeline'),
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
    if overdue.filter(is_go_blocker=True).exists() or overdue.filter(importance=Importance.HIGH).exists():
        return True
    # Trong 14 ngày trước ra mắt, điều kiện dữ liệu còn thiếu cũng đưa kế hoạch sang Có rủi ro.
    if plan.days_to_launch <= 14:
        from .gates import gate_pack

        return any(not row['ok'] and row.get('data') for row in gate_pack(plan))
    return False


def refresh_risk(plan: LaunchPlan, user=None) -> None:
    """Tự gán / gỡ trạng thái «Có rủi ro» khi đang chuẩn bị."""
    if plan.status not in PREPARING_STATUSES:
        return
    risky = is_risky(plan)
    if risky and plan.status == Status.PREPARING:
        set_status(plan, Status.AT_RISK, user, 'Tự động: có việc quan trọng trễ hạn hoặc rủi ro mức Cao.')
    elif not risky and plan.status == Status.AT_RISK:
        set_status(plan, Status.PREPARING, user, 'Tự động: đã xử lý các việc trễ / rủi ro mức Cao.')


def go_conditions(plan: LaunchPlan, tasks=None, links=None) -> list[dict]:
    from .gates import gate_pack

    return gate_pack(plan, links=links, tasks=tasks)


# ---------------------------------------------------------------------------
# Công việc & rủi ro
# ---------------------------------------------------------------------------

TASK_FILE_MAX_BYTES = 50 * 1024 * 1024
TASK_FILE_BLOCKED_EXT = frozenset({'.exe', '.bat', '.cmd', '.com', '.msi', '.ps1', '.sh', '.js', '.vbs', '.html', '.htm', '.svg'})


def _check_files(files) -> None:
    import os

    for f in files or []:
        if (f.size or 0) > TASK_FILE_MAX_BYTES:
            raise WorkflowError(f'Tệp «{f.name}» vượt quá 50 MB.')
        if os.path.splitext(f.name)[1].lower() in TASK_FILE_BLOCKED_EXT:
            raise WorkflowError(f'Không nhận loại tệp «{f.name}».')


def save_task_files(task: LaunchTask, user, files) -> int:
    import os

    from .models import LaunchTaskFile

    count = 0
    for f in files or []:
        row = LaunchTaskFile(
            task=task, uploaded_by=user, original_name=os.path.basename(f.name)[:255], size=f.size or 0,
        )
        row.file.save(f.name, f, save=False)
        row.save()
        count += 1
    return count


def delete_task_file(task_file, user) -> None:
    task = task_file.task
    name = task_file.display_name
    try:
        task_file.file.delete(save=False)
    except OSError:
        pass
    task_file.delete()
    log(task.plan, user, 'task_file', f'Xóa tệp «{name}» của công việc «{task.title}».')


def update_task(task: LaunchTask, user, *, status: str, evidence: str, delay_reason: str,
                owner=None, due_date: date | None = None, can_assign: bool = False,
                start_date: date | None = None, collaborators=None, files=None) -> None:
    today = timezone.localdate()
    if status not in TaskStatus.values:
        raise WorkflowError('Trạng thái công việc không hợp lệ.')
    evidence = (evidence or '').strip()
    delay_reason = (delay_reason or '').strip()
    _check_files(files)
    effective_due = due_date if (can_assign and due_date) else task.due_date
    effective_start = start_date if (can_assign and start_date) else task.start_date
    if effective_start and effective_start > effective_due:
        raise WorkflowError('Ngày bắt đầu phải trước hoặc bằng hạn hoàn thành.')
    if status == TaskStatus.BLOCKED and not delay_reason:
        raise WorkflowError('Ghi rõ vướng mắc khi chuyển công việc sang «Vướng mắc».')
    if status == TaskStatus.DONE:
        if task.is_go_blocker and not evidence and not files and not task.files.exists():
            raise WorkflowError('Điều kiện Go/No-Go cần ghi bằng chứng hoặc đính kèm tệp khi hoàn thành.')
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
        if start_date and start_date != task.start_date:
            changes.append(f'bắt đầu {start_date:%d/%m}')
            task.start_date = start_date
    task.evidence = evidence
    task.delay_reason = delay_reason
    task.save()
    if can_assign and collaborators is not None:
        new_ids = {u.pk for u in collaborators if u.pk != task.owner_id}
        old_ids = set(task.collaborators.values_list('pk', flat=True))
        if new_ids != old_ids:
            task.collaborators.set(new_ids)
            changes.append('người phối hợp: ' + (', '.join(display_name(u) for u in collaborators if u.pk in new_ids) or 'không'))
    added = save_task_files(task, user, files)
    if added:
        changes.append(f'đính kèm {added} tệp')
    log(task.plan, user, 'task', f'Công việc «{task.title}»: ' + (', '.join(changes) if changes else 'cập nhật ghi chú') + '.')
    refresh_risk(task.plan, user)


def add_task(plan: LaunchPlan, user, *, group: str, title: str, due_date: date, owner, importance: str,
             is_go_blocker: bool, deliverable: str = '', start_date: date | None = None,
             collaborators=None) -> LaunchTask:
    if start_date and start_date > due_date:
        raise WorkflowError('Ngày bắt đầu phải trước hoặc bằng hạn hoàn thành.')
    task = LaunchTask.objects.create(
        plan=plan, group=group, title=title.strip(), deliverable=(deliverable or '').strip(),
        offset_days=(due_date - plan.launch_date).days, start_date=start_date, due_date=due_date, owner=owner,
        importance=importance, is_go_blocker=is_go_blocker, sort_order=900,
    )
    if collaborators:
        task.collaborators.set([u.pk for u in collaborators if u.pk != owner.pk])
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
                'Chưa đủ điều kiện bắt buộc: ' + '; '.join(missing[:8])
                + ('…' if len(missing) > 8 else '') + '. Dùng «Ra mắt có điều kiện» nếu vẫn ra mắt.'
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
