"""Tiến trình xử lý một đề xuất — dùng cho danh sách «Đề xuất của tôi» và «Theo dõi tiến trình».

Tính hoàn toàn từ ``steps`` đã prefetch (không query thêm mỗi dòng).
"""

from __future__ import annotations

from .models import ServiceRequest, ServiceRequestStep

STATE_DONE = 'done'
STATE_CURRENT = 'current'
STATE_REJECTED = 'rejected'
STATE_UPCOMING = 'upcoming'
STATE_PLANNED = 'planned'  # Bước chưa tạo (sinh sau khi Thu mua báo giá).

REQUEST_STATUS_BADGES = {
    ServiceRequest.STATUS_IN_PROGRESS: 'bg-warning-subtle text-warning-emphasis border border-warning-subtle',
    ServiceRequest.STATUS_COMPLETED: 'bg-success-subtle text-success-emphasis border border-success-subtle',
    ServiceRequest.STATUS_REJECTED: 'bg-danger-subtle text-danger-emphasis border border-danger-subtle',
    ServiceRequest.STATUS_CANCELLED: 'bg-secondary-subtle text-secondary-emphasis border',
}

_POST_QUOTE_PLACEHOLDER = 'Duyệt chi phí → Đặt hàng → Nhận hàng'


def _person_name(user):
    if not user:
        return ''
    profile = getattr(user, 'profile', None)
    return (profile.full_name if profile and profile.full_name else '') or user.get_full_name() or user.username


def _handler_label(step):
    if step.assignee_id:
        return _person_name(step.assignee)
    if step.target_department_id:
        return f'{step.target_department.name} (chờ tiếp nhận)'
    return 'Chờ tiếp nhận'


def build_progress(service_request, user=None) -> dict:
    steps = sorted(
        (s for s in service_request.steps.all() if s.status != ServiceRequestStep.STATUS_SKIPPED),
        key=lambda s: s.step_order,
    )

    trail = []
    current = None
    rejected = None
    done_count = 0
    my_done = []
    for step in steps:
        if step.status == ServiceRequestStep.STATUS_COMPLETED:
            state = STATE_DONE
            done_count += 1
            if user is not None and step.assignee_id == user.id:
                my_done.append(step.name)
        elif step.status == ServiceRequestStep.STATUS_REJECTED:
            state = STATE_REJECTED
            rejected = step
        elif step.status in ServiceRequestStep.OPEN_HANDLER_STATUSES and current is None:
            state = STATE_CURRENT
            current = step
        else:
            state = STATE_UPCOMING
        trail.append({'name': step.name, 'state': state})

    # Đề xuất mua hàng: các bước duyệt chi phí / đặt hàng chỉ sinh sau khi báo giá xong.
    quote_open = any(
        s.step_code == ServiceRequestStep.STEP_PROCUREMENT_QUOTE
        and s.status != ServiceRequestStep.STATUS_COMPLETED
        for s in steps
    )
    if service_request.is_open and service_request.is_asset_purchase and quote_open:
        trail.append({'name': _POST_QUOTE_PLACEHOLDER, 'state': STATE_PLANNED})

    total = len(trail) or 1
    if service_request.status == ServiceRequest.STATUS_COMPLETED:
        percent = 100
    else:
        percent = round(done_count * 100 / total)

    status = service_request.status
    if status == ServiceRequest.STATUS_IN_PROGRESS and current:
        headline = current.name
        position = steps.index(current) + 1
        detail = f'Đang chờ: {_handler_label(current)}'
    elif status == ServiceRequest.STATUS_REJECTED and rejected:
        headline = f'Bị từ chối tại: {rejected.name}'
        position = steps.index(rejected) + 1
        reason = (rejected.note or '').strip()
        detail = f'Lý do: {reason}' if reason else ''
    elif status == ServiceRequest.STATUS_COMPLETED:
        headline = 'Đã hoàn thành'
        position = len(steps)
        detail = ''
    elif status == ServiceRequest.STATUS_CANCELLED:
        headline = 'Người gửi đã hủy'
        position = done_count
        detail = ''
    else:
        headline = '—'
        position = done_count
        detail = ''

    return {
        'trail': trail,
        'total': len(trail),
        'position': position,
        'percent': percent,
        'headline': headline,
        'detail': detail,
        'current_step': current,
        'my_done': my_done,
        'status_badge': REQUEST_STATUS_BADGES.get(status, 'bg-light text-dark border'),
    }


def attach_progress(requests, user=None):
    for item in requests:
        item.progress = build_progress(item, user=user)
    return requests


# ---- «Chờ tôi xử lý» -------------------------------------------------------

KIND_APPROVE = 'approve'
KIND_EXECUTE = 'execute'

_ACTION_LABELS = {
    ServiceRequestStep.STEP_TEAM_LEADER: 'Duyệt',
    ServiceRequestStep.STEP_DIVISION_HEAD: 'Duyệt',
    ServiceRequestStep.STEP_DEPARTMENT_HEAD: 'Duyệt',
    ServiceRequestStep.STEP_ACCOUNTANT: 'Duyệt chi phí',
    ServiceRequestStep.STEP_DIRECTOR: 'Duyệt chi phí',
    ServiceRequestStep.STEP_PROCUREMENT_QUOTE: 'Báo giá NCC',
    ServiceRequestStep.STEP_ADVANCE: 'Chi tạm ứng',
    ServiceRequestStep.STEP_PURCHASE: 'Đặt hàng',
    ServiceRequestStep.STEP_RECEIPT: 'Xác nhận nhận hàng',
    ServiceRequestStep.STEP_GENERAL_EXECUTION: 'Thực hiện',
}


def _step_opened_at(step, steps):
    """Thời điểm bước bắt đầu chờ: lúc bước phụ thuộc hoàn thành, không có thì lúc gửi phiếu."""
    if step.depends_on_id:
        for other in steps:
            if other.pk == step.depends_on_id and other.completed_at:
                return other.completed_at
    return step.request.created_at


def describe_pending_step(step, user) -> dict:
    """Mô tả một bước trong «Chờ tôi xử lý»: việc cần làm, lý do nằm trong hàng đợi, thời gian chờ."""
    from hrm.permissions import is_director

    request_obj = step.request
    steps = list(request_obj.steps.all())

    action = _ACTION_LABELS.get(step.step_code, 'Duyệt' if step.is_approval else 'Thực hiện')
    if step.step_code == ServiceRequestStep.STEP_DIVISION_HEAD and request_obj.is_asset_purchase:
        action = 'Duyệt & giao Thu mua'

    if step.assignee_id == user.id:
        reason = 'Được giao cho bạn'
    elif step.assignee_id:
        # Chỉ GĐ thấy bước đã gán người khác (duyệt thay TBP / TP).
        reason = f'Duyệt thay {_person_name(step.assignee)}' if is_director(user) else 'Được giao'
    elif step.target_department_id:
        reason = f'Hàng đợi {step.target_department.name}'
    else:
        reason = 'Chưa có người nhận — tiếp nhận thay'

    return {
        'action': action,
        'kind': KIND_APPROVE if step.is_approval else KIND_EXECUTE,
        'needs_claim': not step.assignee_id,
        'reason': reason,
        'waiting_since': _step_opened_at(step, steps),
        'progress': build_progress(request_obj, user=user),
    }


def attach_pending_info(steps, user):
    for step in steps:
        step.info = describe_pending_step(step, user)
    return steps
