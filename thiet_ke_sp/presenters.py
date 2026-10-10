"""Dữ liệu hiển thị: thanh 8 bước, cột thông tin bên phải, ảnh đại diện, cờ quyền từng nút."""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from thiet_ke_sp import permissions as perms
from thiet_ke_sp.models import (
    DOSSIER_ROLE_FIELDS,
    FINAL_STATUSES,
    STEPS,
    Attachment,
    AttachmentKind,
    AuditLog,
    ProductDevelopment,
    Role,
    Status,
)
from thiet_ke_sp.services import workflow as wf

APPROVAL_STATUSES = (Status.BRIEF_PENDING, Status.DESIGN_PENDING, Status.MASTER_PENDING)


def effective_status(dossier: ProductDevelopment) -> str:
    """Trạng thái nghiệp vụ thật khi hồ sơ đang tạm dừng / đã hủy (để tô thanh bước)."""
    if dossier.status == Status.PAUSED and dossier.paused_from_status:
        return dossier.paused_from_status
    if dossier.status == Status.CANCELLED:
        last = (
            AuditLog.objects.filter(dossier=dossier, to_status=Status.CANCELLED)
            .values_list('from_status', flat=True).first()
        )
        if last == Status.PAUSED:
            last = dossier.paused_from_status or last
        return last or Status.DRAFT
    return dossier.status


def stepper(dossier: ProductDevelopment) -> list[dict]:
    status = effective_status(dossier)
    current = 0
    for index, (_key, _label, statuses) in enumerate(STEPS):
        if status in statuses:
            current = index
            break
    finished = dossier.status in (Status.HANDED_OVER, Status.CLOSED)
    rows = []
    for index, (key, label, _statuses) in enumerate(STEPS):
        if index < current or (finished and index == current and dossier.status == Status.CLOSED):
            state = 'done'
        elif index == current:
            state = 'current'
        else:
            state = 'todo'
        rows.append({'key': key, 'label': label, 'no': index + 1, 'state': state})
    return rows


def roles_rail(dossier: ProductDevelopment) -> list[dict]:
    rows = [{'role': Role.PROPOSER, 'label': Role.PROPOSER.label, 'user': dossier.proposer}]
    for role in DOSSIER_ROLE_FIELDS:
        rows.append({'role': role, 'label': Role(role).label, 'user': getattr(dossier, role)})
    return rows


def _margin(price, cost):
    if price is None or cost is None or not price:
        return None, None
    value = price - cost
    return value, (value * 100 / price).quantize(Decimal('0.1'))


def costing_summary(dossier: ProductDevelopment) -> dict:
    cost = dossier.cost_for_variance
    wholesale = dossier.proposed_wholesale_price or dossier.target_wholesale_price
    retail = dossier.proposed_retail_price or dossier.target_retail_price
    wholesale_margin, wholesale_margin_pct = _margin(wholesale, cost)
    retail_margin, retail_margin_pct = _margin(retail, cost)
    return {
        'cost': cost,
        'cost_label': 'Giá thành sau mẫu' if dossier.post_sample_cost is not None else 'Giá thành dự kiến',
        'variance': dossier.cost_variance,
        'variance_pct': dossier.cost_variance_pct,
        'wholesale': wholesale,
        'retail': retail,
        'wholesale_margin': wholesale_margin,
        'wholesale_margin_pct': wholesale_margin_pct,
        'retail_margin': retail_margin,
        'retail_margin_pct': retail_margin_pct,
    }


def due_progress(dossier: ProductDevelopment, task) -> int | None:
    """% thời gian đã dùng của bước hiện tại (từ lúc vào bước tới hạn)."""
    if task is None or not task.due_at:
        return None
    start = dossier.status_changed_at
    total = (task.due_at - start).total_seconds()
    if total <= 0:
        return 100
    used = (timezone.now() - start).total_seconds()
    return max(0, min(100, round(used * 100 / total)))


def dossier_age_days(dossier: ProductDevelopment) -> int:
    end = dossier.closed_at or timezone.now()
    return max((end - dossier.created_at).days, 0)


STAGE_BARS = (
    ('Đề bài', (Status.DRAFT, Status.BRIEF_PENDING, Status.BRIEF_NEEDS_INFO)),
    ('Thiết kế', (Status.DESIGNING, Status.DESIGN_PENDING, Status.DESIGN_REVISE)),
    ('Làm mẫu', (Status.SAMPLING, Status.SAMPLE_REVISE)),
    ('Đánh giá', (Status.SAMPLE_EVAL_PENDING,)),
    ('Duyệt chuẩn', (Status.MASTER_PENDING,)),
    ('Bàn giao', (Status.APPROVED, Status.HANDED_OVER)),
)


def stage_bars(status_rows: list[dict]) -> list[dict]:
    counts = {row['value']: row['count'] for row in status_rows}
    bars = [
        {'label': label, 'count': sum(counts.get(s, 0) for s in statuses),
         'query': '&'.join(f'status={s}' for s in statuses), 'first_status': statuses[0]}
        for label, statuses in STAGE_BARS
    ]
    peak = max((b['count'] for b in bars), default=0) or 1
    for b in bars:
        b['height'] = max(round(b['count'] * 100 / peak), 4)
    return bars


KANBAN_COLUMNS = (
    ('proposal', 'Đề xuất', (Status.DRAFT, Status.BRIEF_NEEDS_INFO)),
    ('brief', 'Chờ duyệt đề bài', (Status.BRIEF_PENDING,)),
    ('design', 'Thiết kế', (Status.DESIGNING, Status.DESIGN_REVISE)),
    ('design_approval', 'Chờ duyệt thiết kế', (Status.DESIGN_PENDING,)),
    ('sample', 'Làm mẫu', (Status.SAMPLING, Status.SAMPLE_REVISE)),
    ('evaluation', 'Đánh giá mẫu', (Status.SAMPLE_EVAL_PENDING,)),
    ('master', 'Duyệt mẫu chuẩn', (Status.MASTER_PENDING,)),
    ('handover', 'Duyệt SX / bàn giao', (Status.APPROVED, Status.HANDED_OVER)),
    ('paused', 'Tạm dừng', (Status.PAUSED,)),
)
KANBAN_STATUSES = tuple(s for _key, _label, statuses in KANBAN_COLUMNS for s in statuses)
KANBAN_COLUMN_OF = {s: key for key, _label, statuses in KANBAN_COLUMNS for s in statuses}
KANBAN_LABELS = {key: label for key, label, _statuses in KANBAN_COLUMNS}

# Thao tác kéo thả: (nhãn xác nhận, bắt buộc ý kiến, cần mã chính thức).
KANBAN_MOVE_SPECS = {
    'submit_brief': ('Gửi duyệt đề bài', False, False),
    'brief_approve': ('Duyệt đề bài', False, False),
    'brief_request_change': ('Yêu cầu bổ sung đề bài', True, False),
    'design_submit': ('Gửi duyệt thiết kế', False, False),
    'design_approve': ('Duyệt thiết kế', False, False),
    'design_request_change': ('Yêu cầu chỉnh thiết kế', True, False),
    'sample_submit': ('Gửi đánh giá mẫu', False, False),
    'master_submit': ('Trình duyệt mẫu chuẩn', False, False),
    'sample_fix': ('Yêu cầu sửa mẫu', True, False),
    'master_approve': ('Duyệt mẫu chuẩn — sản xuất', False, True),
    'master_request_fix': ('Yêu cầu sửa mẫu', True, False),
    'eval_request_design': ('Yêu cầu chỉnh thiết kế', True, False),
    'master_request_design': ('Yêu cầu chỉnh thiết kế', True, False),
    'pause': ('Tạm dừng hồ sơ', True, False),
    'resume': ('Tiếp tục hồ sơ', False, False),
}
_KANBAN_STEP_MOVES = {
    Status.DRAFT: {'brief': 'submit_brief'},
    Status.BRIEF_NEEDS_INFO: {'brief': 'submit_brief'},
    Status.BRIEF_PENDING: {'design': 'brief_approve', 'proposal': 'brief_request_change'},
    Status.DESIGNING: {'design_approval': 'design_submit'},
    Status.DESIGN_REVISE: {'design_approval': 'design_submit'},
    Status.DESIGN_PENDING: {'sample': 'design_approve', 'design': 'design_request_change'},
    Status.SAMPLING: {'evaluation': 'sample_submit'},
    Status.SAMPLE_REVISE: {'evaluation': 'sample_submit'},
    Status.SAMPLE_EVAL_PENDING: {'master': 'master_submit', 'sample': 'sample_fix', 'design': 'eval_request_design'},
    Status.MASTER_PENDING: {'handover': 'master_approve', 'sample': 'master_request_fix',
                            'design': 'master_request_design'},
}


def kanban_moves_for_status(dossier: ProductDevelopment) -> dict[str, str]:
    """Cột đích → thao tác, chỉ theo trạng thái (chưa xét quyền)."""
    status = dossier.status
    if status == Status.PAUSED:
        target = KANBAN_COLUMN_OF.get(dossier.paused_from_status)
        return {target: 'resume'} if target else {}
    moves = dict(_KANBAN_STEP_MOVES.get(status, {}))
    if status in wf.PAUSABLE:
        moves['paused'] = 'pause'
    return moves


def _can_kanban_move(dossier: ProductDevelopment, user, move: str, cache: dict) -> bool:
    def approver():
        if 'approver' not in cache:
            cache['approver'] = perms.is_dossier_approver(dossier, user)
        return cache['approver']

    if move == 'submit_brief':
        return perms.can_edit_brief(dossier, user)
    if move == 'design_submit':
        return perms.can_work_as(dossier, user, Role.DESIGNER, Role.OWNER)
    if move == 'sample_submit':
        return perms.can_work_as(dossier, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
    if move in ('master_submit', 'sample_fix', 'eval_request_design'):
        return perms.can_work_as(dossier, user, Role.OWNER)
    return approver()


def kanban_moves(dossier: ProductDevelopment, user) -> dict[str, str]:
    """Cột đích → thao tác mà người dùng được phép kéo thả."""
    cache: dict = {}
    return {
        col: move for col, move in kanban_moves_for_status(dossier).items()
        if _can_kanban_move(dossier, user, move, cache)
    }


def kanban_columns(rows: list, limit: int = 40) -> list[dict]:
    columns = []
    for key, label, statuses in KANBAN_COLUMNS:
        items = [d for d in rows if d.status in statuses]
        columns.append({
            'key': key,
            'label': label,
            'count': len(items),
            'late': sum(1 for d in items if getattr(d, 'step_late_days', 0)),
            'items': items[:limit],
            'more': max(len(items) - limit, 0),
            'query': '&'.join(f'status={s}' for s in statuses),
        })
    return columns


def dashboard_alerts(data: dict, user, limit: int = 5) -> list[dict]:
    alerts = []
    for t in data['overdue_tasks'][:3]:
        alerts.append({
            'tone': 'red', 'url': t.dossier.get_absolute_url(),
            'title': f'{t.dossier.name} trễ {t.days_late} ngày',
            'body': f'{t.title} · {perms.display_name(t.assignee) or "Chưa giao"}',
        })
    waiting = (
        ProductDevelopment.objects.filter(approver=user, status__in=APPROVAL_STATUSES, is_demo=False)
        .order_by('status_changed_at')[:3]
    )
    for d in waiting:
        alerts.append({
            'tone': 'blue', 'url': f'{d.get_absolute_url()}?tab=approval',
            'title': f'{d.name} chờ bạn duyệt', 'body': f'{d.code} · {d.get_status_display()}',
        })
    for t in data['due_soon_tasks'][:3]:
        alerts.append({
            'tone': 'amber', 'url': t.dossier.get_absolute_url(),
            'title': f'{t.dossier.name} sắp đến hạn',
            'body': f'{t.title} · {perms.display_name(t.assignee) or "Chưa giao"}',
        })
    return alerts[:limit]


def step_checklist(dossier: ProductDevelopment) -> tuple[str, list[tuple[str, bool]]]:
    status = dossier.status
    if status in (Status.DESIGNING, Status.DESIGN_REVISE):
        return 'Điều kiện gửi duyệt thiết kế', wf.design_checklist_all(dossier)
    if status in (Status.SAMPLE_EVAL_PENDING, Status.MASTER_PENDING):
        return 'Điều kiện duyệt mẫu chuẩn', wf.master_checklist(dossier)
    if status in (Status.APPROVED, Status.HANDED_OVER, Status.CLOSED):
        return 'Điều kiện bàn giao sản xuất', wf.handover_checklist(dossier)
    if status in (Status.DRAFT, Status.BRIEF_NEEDS_INFO, Status.BRIEF_PENDING):
        return 'Thông tin đề bài', [
            (label, bool(getattr(dossier, field, None))) for field, label in wf.BRIEF_REQUIRED
        ]
    return '', []


def cover_map(dossier_ids) -> dict[int, Attachment]:
    """Ảnh đại diện: mặt trước của bản thiết kế hiện hành → ảnh mẫu → ảnh tham khảo."""
    ids = list(dossier_ids)
    result: dict[int, Attachment] = {}
    if not ids:
        return result
    base = Attachment.objects.filter(dossier_id__in=ids, is_deleted=False, is_current=True)
    priority = (
        base.filter(kind=AttachmentKind.FRONT, design_version__is_current=True),
        base.filter(kind=AttachmentKind.FRONT),
        base.filter(kind=AttachmentKind.SAMPLE_PHOTO, sample_version__is_current=True),
        base.filter(kind=AttachmentKind.PRODUCT_PHOTO),
        base.filter(kind__in=(AttachmentKind.REFERENCE, AttachmentKind.COLORWAY)),
    )
    for qs in priority:
        for att in qs.order_by('-uploaded_at'):
            if att.dossier_id not in result and att.is_image:
                result[att.dossier_id] = att
        if len(result) == len(ids):
            break
    return result


def action_flags(dossier: ProductDevelopment, user) -> dict[str, bool]:
    s = dossier.status
    approver = perms.is_dossier_approver(dossier, user)
    owner = perms.can_work_as(dossier, user, Role.OWNER)
    dvs = dossier.current_design_versions()
    sv = dossier.current_sample_version()
    design_open = s in (Status.DESIGNING, Status.DESIGN_REVISE) and any(dv.is_editable for dv in dvs)
    sample_open = s in (Status.SAMPLING, Status.SAMPLE_REVISE) and sv is not None and sv.is_editable
    designer = perms.can_work_as(dossier, user, Role.DESIGNER, Role.OWNER)
    return {
        'edit_brief': perms.can_edit_brief(dossier, user),
        'submit_brief': s in (Status.DRAFT, Status.BRIEF_NEEDS_INFO) and perms.can_edit_brief(dossier, user),
        'delete_draft': s == Status.DRAFT and perms.can_delete(user)
        and perms.has_role(dossier, user, Role.PROPOSER, Role.OWNER),
        'decide_brief': s == Status.BRIEF_PENDING and approver,
        'edit_design': design_open and designer,
        'add_design_option': design_open and designer and len(dvs) < wf.MAX_DESIGN_OPTIONS,
        'drop_design_option': design_open and designer and len(dvs) > 1,
        'decide_design': s == Status.DESIGN_PENDING and approver,
        'request_design_change': (s == Status.SAMPLE_EVAL_PENDING and owner) or (s == Status.MASTER_PENDING and approver),
        'edit_sample': sample_open and perms.can_work_as(dossier, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER),
        'edit_tech_pack': sample_open and perms.can_work_as(dossier, user, Role.TECHNICIAN, Role.OWNER),
        'evaluate': s == Status.SAMPLE_EVAL_PENDING and perms.can_act(dossier, user)
        and bool(wf.evaluator_roles_for(dossier, user)),
        'request_fix': (s == Status.SAMPLE_EVAL_PENDING and owner) or (s == Status.MASTER_PENDING and approver),
        'submit_master': s == Status.SAMPLE_EVAL_PENDING and owner,
        'decide_master': s == Status.MASTER_PENDING and approver,
        'edit_costing': not dossier.is_locked and s not in (Status.DRAFT, *FINAL_STATUSES)
        and perms.can_work_as(dossier, user, Role.COSTING, Role.OWNER),
        'handover': s == Status.APPROVED and perms.can_work_as(dossier, user, Role.OWNER, Role.TECHNICIAN),
        'close': s == Status.HANDED_OVER and owner,
        'change_request': s == Status.APPROVED and (approver or owner),
        'pause': s in wf.PAUSABLE and approver,
        'resume': s == Status.PAUSED and approver,
        'cancel': s not in (*FINAL_STATUSES, Status.DRAFT, Status.HANDED_OVER) and approver,
        'edit_roles': perms.can_edit_roles(dossier, user),
        'manage_due': s not in FINAL_STATUSES and (perms.has_role(dossier, user, Role.OWNER) or approver),
        'comment': perms.can_view_dossier(dossier, user) and s not in FINAL_STATUSES,
    }
