"""Dữ liệu hiển thị: thanh 5 bước, cột thông tin bên phải, ảnh đại diện, cờ quyền từng nút."""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from thiet_ke_sp import permissions as perms
from thiet_ke_sp.models import (
    DOSSIER_ROLE_FIELDS,
    ROLE_PARTNER,
    FINAL_STATUSES,
    APPROVER_DECIDE_STATUSES,
    DESIGN_APPROVAL_STATUSES,
    STEPS,
    Attachment,
    AttachmentKind,
    AuditLog,
    DesignVersion,
    ProductDevelopment,
    Role,
    SampleVersion,
    Status,
)
from thiet_ke_sp.services import workflow as wf

APPROVAL_STATUSES = APPROVER_DECIDE_STATUSES


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
    current = len(STEPS)
    for index, (_key, _label, statuses) in enumerate(STEPS):
        if status in statuses:
            current = index
            break
    finished = current >= len(STEPS)
    rows = []
    for index, (key, label, _statuses) in enumerate(STEPS):
        if index < current or (finished and index == current):
            state = 'done'
        elif index == current:
            state = 'current'
        else:
            state = 'todo'
        rows.append({'key': key, 'label': label, 'no': index + 1, 'state': state})
    return rows


def step_is_reached(dossier: ProductDevelopment, step: str) -> bool:
    """Bước đã đi tới (đang làm, đã xong, hoặc từng tới rồi quay lại) thì mới mở tab."""
    if any(row['key'] == step and row['state'] != 'todo' for row in stepper(dossier)):
        return True
    furthest = wf._rewind_rank_seen(dossier)
    index = next((i for i, (key, _label, _statuses) in enumerate(STEPS) if key == step), None)
    return furthest is not None and index is not None and index <= furthest


# Tab công đoạn chỉ mở khi hồ sơ đã tới bước đó. Các tab còn lại luôn mở.
_TAB_STEP = {
    'design': 'design',
    'technical': 'technical',
    'sample': 'sample',
    'approval': 'design_approval',
}
_REOPEN_PROCESS_TABS = frozenset({'overview', 'design', 'technical', 'sample'})
_REOPEN_ALWAYS_TABS = frozenset({'costing', 'approval', 'files', 'history'})


def tab_is_open(dossier: ProductDevelopment, key: str) -> bool:
    """Khi huỷ hoàn thành chỉ mở đúng công đoạn đang sửa + Giá thành / Phê duyệt / Trao đổi / Lịch sử."""
    if dossier.status == Status.LIBRARY_REOPEN:
        edit_step = wf.reopen_edit_step(dossier)
        if edit_step:
            if key in _REOPEN_ALWAYS_TABS or key == edit_step:
                return True
            if key in _REOPEN_PROCESS_TABS:
                return False
    step = _TAB_STEP.get(key)
    if step is None:
        return True
    return step_is_reached(dossier, step)


def default_open_tab(dossier: ProductDevelopment) -> str:
    """Tab mặc định khi URL không có tab hoặc tab đang bị khóa."""
    if dossier.status == Status.LIBRARY_REOPEN:
        edit_step = wf.reopen_edit_step(dossier)
        if edit_step and tab_is_open(dossier, edit_step):
            return edit_step
    for key in ('overview', 'design', 'technical', 'sample', 'costing', 'approval', 'files', 'history'):
        if tab_is_open(dossier, key):
            return key
    return 'overview'


def roles_rail(dossier: ProductDevelopment) -> list[dict]:
    rows = [{'role': Role.PROPOSER, 'label': Role.PROPOSER.label, 'user': dossier.proposer}]
    for role in DOSSIER_ROLE_FIELDS:
        rows.append({'role': role, 'label': Role(role).label, 'user': getattr(dossier, role)})
        if role == Role.OWNER and dossier.co_owner_id:
            rows.append({'role': role, 'label': Role.OWNER.label, 'user': dossier.co_owner})
        partner = ROLE_PARTNER.get(role)
        if partner and getattr(dossier, f'{partner}_id'):
            rows.append({'role': role, 'label': Role(role).label, 'user': getattr(dossier, partner)})
    followers = list(dossier.followers.select_related('profile'))
    if followers:
        for person in followers:
            rows.append({'role': Role.FOLLOWER, 'label': Role.FOLLOWER.label, 'user': person})
    else:
        rows.append({'role': Role.FOLLOWER, 'label': Role.FOLLOWER.label, 'user': None})
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
    ('Đề xuất', (Status.DRAFT, Status.BRIEF_PENDING, Status.BRIEF_NEEDS_INFO)),
    ('Thiết kế', (Status.DESIGNING, Status.DESIGN_PENDING, Status.DESIGN_REVISE)),
    ('Kỹ thuật', (Status.TECHNICAL, Status.TECHNICAL_REVISE)),
    ('Làm mẫu', (Status.SAMPLING, Status.SAMPLE_REVISE, Status.LIBRARY_REOPEN)),
    ('Duyệt thiết kế', (Status.SAMPLE_EVAL_PENDING, Status.MASTER_PENDING)),
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
    ('design', 'Thiết kế', (Status.DESIGNING, Status.DESIGN_REVISE)),
    ('technical', 'Kỹ thuật', (Status.TECHNICAL, Status.TECHNICAL_REVISE)),
    ('sample', 'Làm mẫu', (Status.SAMPLING, Status.SAMPLE_REVISE, Status.LIBRARY_REOPEN)),
    ('design_approval', 'Duyệt thiết kế', (Status.SAMPLE_EVAL_PENDING, Status.MASTER_PENDING)),
    ('paused', 'Tạm dừng', (Status.PAUSED,)),
)
KANBAN_STATUSES = tuple(s for _key, _label, statuses in KANBAN_COLUMNS for s in statuses)
KANBAN_COLUMN_OF = {s: key for key, _label, statuses in KANBAN_COLUMNS for s in statuses}
KANBAN_LABELS = {key: label for key, label, _statuses in KANBAN_COLUMNS}

# Thao tác kéo thả: (nhãn xác nhận, bắt buộc ý kiến, cần mã chính thức).
KANBAN_MOVE_SPECS = {
    'submit_brief': ('Chuyển sang thiết kế', False, False),
    'brief_approve': ('Duyệt đề bài', False, False),
    'brief_request_change': ('Yêu cầu bổ sung đề bài', True, False),
    'design_submit': ('Chuyển kỹ thuật', False, False),
    'technical_submit': ('Chuyển làm mẫu', False, False),
    'design_approve': ('Duyệt thiết kế', False, False),
    'design_request_change': ('Yêu cầu chỉnh thiết kế', True, False),
    'sample_submit': ('Gửi duyệt thiết kế', False, False),
    'master_submit': ('Trình duyệt mẫu chuẩn', False, False),
    'sample_fix': ('Yêu cầu sửa mẫu', True, False),
    'master_approve': ('Duyệt thiết kế', False, True),
    'master_request_fix': ('Yêu cầu sửa mẫu', True, False),
    'eval_request_design': ('Yêu cầu chỉnh thiết kế', True, False),
    'eval_request_technical': ('Yêu cầu chỉnh kỹ thuật', True, False),
    'master_request_design': ('Yêu cầu chỉnh thiết kế', True, False),
    'master_request_technical': ('Yêu cầu chỉnh kỹ thuật', True, False),
    'pause': ('Tạm dừng hồ sơ', True, False),
    'resume': ('Tiếp tục hồ sơ', False, False),
    'resubmit_approval': ('Gửi duyệt thiết kế', False, False),
}
_KANBAN_STEP_MOVES = {
    Status.DRAFT: {'design': 'submit_brief'},
    Status.BRIEF_NEEDS_INFO: {'design': 'submit_brief'},
    Status.DESIGNING: {'technical': 'design_submit'},
    Status.DESIGN_REVISE: {'technical': 'design_submit'},
    Status.TECHNICAL: {'sample': 'technical_submit'},
    Status.TECHNICAL_REVISE: {'sample': 'technical_submit'},
    Status.SAMPLING: {'design_approval': 'sample_submit'},
    Status.SAMPLE_REVISE: {'design_approval': 'sample_submit'},
    Status.SAMPLE_EVAL_PENDING: {
        'sample': 'sample_fix', 'design': 'eval_request_design',
        'technical': 'eval_request_technical',
    },
    Status.MASTER_PENDING: {
        'sample': 'master_request_fix', 'design': 'master_request_design',
        'technical': 'master_request_technical',
    },
    Status.LIBRARY_REOPEN: {'design_approval': 'resubmit_approval'},
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
    if move == 'technical_submit':
        return perms.can_work_as(dossier, user, Role.TECHNICIAN, Role.OWNER)
    if move == 'sample_submit':
        return perms.can_work_as(dossier, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER)
    if move == 'resubmit_approval':
        return perms.is_participant(dossier, user)
    if move in ('sample_fix', 'eval_request_design', 'eval_request_technical', 'master_submit',
                'master_request_technical'):
        return approver()
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


def step_checklist(dossier: ProductDevelopment, user=None) -> tuple[str, list[tuple[str, bool]]]:
    status = dossier.status
    if status in (Status.DESIGNING, Status.DESIGN_REVISE, Status.DESIGN_PENDING):
        return 'Điều kiện chuyển kỹ thuật', wf.design_checklist_all(dossier)
    if status in DESIGN_APPROVAL_STATUSES:
        return 'Điều kiện duyệt thiết kế', wf.master_checklist(dossier, user)
    if status == Status.LIBRARY_REOPEN:
        return 'Điều kiện khi gửi duyệt thiết kế', wf.master_checklist(dossier, user)
    if status in (Status.APPROVED, Status.HANDED_OVER, Status.CLOSED):
        return 'Điều kiện thêm vào Thư viện', wf.handover_checklist(dossier)
    if status in (Status.DRAFT, Status.BRIEF_NEEDS_INFO, Status.BRIEF_PENDING):
        return 'Thông tin đề bài', [
            (label, bool(getattr(dossier, field, None))) for field, label in wf.BRIEF_REQUIRED
        ]
    return '', []


def cover_map(dossier_ids) -> dict[int, Attachment]:
    """Ảnh đại diện: ảnh 2 mặt của phương án thiết kế hiện hành; không có thì ảnh sản phẩm ở Tổng quan."""
    ids = list(dossier_ids)
    result: dict[int, Attachment] = {}
    if not ids:
        return result
    live = Attachment.objects.filter(dossier_id__in=ids, is_deleted=False)
    fronts = live.filter(
        kind=AttachmentKind.FRONT, is_current=True, design_version__is_current=True,
    ).order_by('design_version__option_no', '-uploaded_at')
    for att in fronts:
        if att.dossier_id not in result and att.is_image:
            result[att.dossier_id] = att
    missing = [pk for pk in ids if pk not in result]
    if not missing:
        return result
    photos = live.filter(
        dossier_id__in=missing, kind=AttachmentKind.PRODUCT_PHOTO,
        design_version__isnull=True, sample_version__isnull=True,
    ).order_by('-uploaded_at')
    for att in photos:
        if att.dossier_id not in result and att.is_image:
            result[att.dossier_id] = att
    return result


def action_flags(dossier: ProductDevelopment, user) -> dict[str, bool]:
    s = dossier.status
    approver = perms.is_dossier_approver(dossier, user)
    owner = perms.can_work_as(dossier, user, Role.OWNER)
    dvs = dossier.current_design_versions()
    sv = dossier.current_sample_version()
    test_edit = wf.test_edit_after_approval(dossier)
    design_reopen = wf.allows_reopen_design(dossier)
    tech_reopen = wf.allows_reopen_technical(dossier)
    sample_reopen = wf.allows_reopen_sample(dossier)
    design_step = s in (Status.DESIGNING, Status.DESIGN_REVISE) and any(dv.is_editable for dv in dvs)
    sample_step = s in (Status.SAMPLING, Status.SAMPLE_REVISE) and sv is not None and sv.is_editable
    design_open = design_step or design_reopen or (test_edit and any(dv.state == DesignVersion.STATE_APPROVED for dv in dvs)) or any(
        wf.design_reopened(dossier, dv) for dv in dvs
    )
    sample_open = sample_step or (sample_reopen and sv is not None) or (
        test_edit and sv is not None and sv.state == SampleVersion.STATE_PASSED
    ) or wf.sample_reopened(dossier, sv)
    tech_open = sv is not None and (
        (s in (Status.TECHNICAL, Status.TECHNICAL_REVISE, Status.SAMPLING, Status.SAMPLE_REVISE) and sv.is_editable)
        or tech_reopen
        or (test_edit and sv.state == SampleVersion.STATE_PASSED)
        or wf.tech_reopened(dossier, sv)
    )
    designer = perms.can_work_as(dossier, user, Role.DESIGNER, Role.OWNER)
    approval_step = s in APPROVER_DECIDE_STATUSES
    return {
        'edit_brief': perms.can_edit_brief(dossier, user) and (
            s != Status.LIBRARY_REOPEN or wf.allows_reopen_overview(dossier)
        ),
        'edit_proposal': (
            s in (Status.DRAFT, Status.BRIEF_NEEDS_INFO, Status.BRIEF_PENDING)
            or wf.allows_reopen_overview(dossier)
        ) and perms.can_edit_brief(dossier, user),
        'submit_brief': s in (Status.DRAFT, Status.BRIEF_NEEDS_INFO) and perms.can_edit_brief(dossier, user),
        'delete_draft': perms.can_delete_dossier(dossier, user),
        'decide_brief': s == Status.BRIEF_PENDING and approver,
        'edit_design': design_open and designer,
        'submit_design': design_step and designer,
        'submit_technical': s in (Status.TECHNICAL, Status.TECHNICAL_REVISE)
        and perms.can_work_as(dossier, user, Role.TECHNICIAN, Role.OWNER),
        'add_design_option': design_step and designer and len(dvs) < wf.MAX_DESIGN_OPTIONS,
        'drop_design_option': design_step and designer and len(dvs) > 1,
        'decide_design': s == Status.DESIGN_PENDING and approver,
        'request_design_change': approval_step and sv is not None and approver,
        'request_technical': approval_step and sv is not None and approver,
        'edit_sample': sample_open and perms.can_work_as(dossier, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER),
        'submit_sample': s in (Status.SAMPLING, Status.SAMPLE_REVISE) and sv is not None
        and perms.can_work_as(dossier, user, Role.SAMPLE_MAKER, Role.TECHNICIAN, Role.OWNER),
        'edit_tech_pack': tech_open and perms.can_work_as(dossier, user, Role.TECHNICIAN, Role.OWNER),
        'evaluate': s in DESIGN_APPROVAL_STATUSES and sv is not None and perms.can_act(dossier, user)
        and bool(wf.evaluator_roles_for(dossier, user)),
        'request_fix': approval_step and sv is not None and approver,
        'submit_master': False,
        'decide_master': approval_step and sv is not None and approver,
        'edit_costing': (not dossier.is_locked or test_edit) and s not in (Status.DRAFT, *FINAL_STATUSES)
        and perms.can_work_as(dossier, user, Role.COSTING, Role.OWNER),
        'test_edit': test_edit,
        'handover': s == Status.APPROVED and perms.can_work_as(dossier, user, Role.OWNER, Role.TECHNICIAN),
        'reopen_completion': s == Status.HANDED_OVER and perms.is_participant(dossier, user),
        'resubmit_approval': s == Status.LIBRARY_REOPEN and perms.is_participant(dossier, user),
        'close': False,
        'change_request': s == Status.APPROVED and (approver or owner),
        'pause': s in wf.PAUSABLE and approver,
        'resume': s == Status.PAUSED and approver,
        'cancel': False,
        'edit_roles': perms.can_edit_roles(dossier, user),
        'manage_due': s not in FINAL_STATUSES and (perms.has_role(dossier, user, Role.OWNER) or approver),
        'comment': perms.can_view_dossier(dossier, user) and s not in FINAL_STATUSES,
        'full_access': perms.has_full_dossier_access(user),
        'rewind': bool(wf.rewind_choices(dossier)) and perms.can_work_as(dossier, user, Role.OWNER),
    }
