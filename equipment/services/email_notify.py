"""Email thông báo module Quản lý thiết bị."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def _from_email() -> str:
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@portal.justplay.vn')


def _portal_base_url() -> str:
    return getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '').rstrip('/')


def _dedupe_emails(addresses) -> list[str]:
    seen = set()
    result = []
    for addr in addresses:
        addr = (addr or '').strip()
        if addr and addr not in seen:
            seen.add(addr)
            result.append(addr)
    return result


def get_it_notify_emails() -> list[str]:
    """Email nhóm IT / cấu hình thêm / superuser fallback."""
    return get_repair_notify_emails('it')


def get_repair_notify_emails(repair_equipment_scope: str | None) -> list[str]:
    """Email phòng xử lý theo phạm vi thiết bị IT / sản xuất."""
    from equipment.scope import SCOPE_PRODUCTION, normalize_repair_equipment_scope
    from equipment.services.managed_department import default_managed_department_for_scope
    from service_requests.workflow_it import get_it_department

    scope = normalize_repair_equipment_scope(repair_equipment_scope)
    emails = []

    extra = getattr(settings, 'EQUIPMENT_NOTIFY_EMAILS', '') or ''
    emails.extend(e.strip() for e in extra.split(',') if e.strip())

    try:
        from hrm.models import Profile

        dept = (
            default_managed_department_for_scope(SCOPE_PRODUCTION)
            if scope == SCOPE_PRODUCTION
            else get_it_department()
        )
        if dept:
            profiles = Profile.objects.filter(
                department=dept,
                is_employed=True,
                user__is_active=True,
            ).select_related('user')
            emails.extend(p.user.email for p in profiles if p.user.email)
    except Exception:
        logger.exception('Không lấy được email phòng xử lý hỗ trợ kỹ thuật')

    if not emails:
        emails.extend(
            User.objects.filter(is_superuser=True, is_active=True)
            .exclude(email='')
            .values_list('email', flat=True)
        )

    return _dedupe_emails(emails)


def _send(subject: str, message: str, recipient_list: list[str]) -> bool:
    if not recipient_list:
        logger.warning('Bỏ qua gửi mail "%s" — không có người nhận.', subject)
        return False
    try:
        send_mail(subject, message, _from_email(), recipient_list, fail_silently=False)
        return True
    except Exception:
        logger.exception('Gửi email thất bại: %s', subject)
        return False


def _device_location(device) -> str:
    parts = [device.usage_department_label]
    if device.usage_room:
        parts.append(device.usage_room)
    return ' · '.join(p for p in parts if p)


def _request_url(service_request_id: int) -> str:
    path = reverse('service_requests:detail', kwargs={'pk': service_request_id})
    base = _portal_base_url()
    return f'{base}{path}' if base else path


def notify_it_new_breakdown(*, device, service_request, reporter_name: str, issue_description: str):
    recipients = get_repair_notify_emails(service_request.effective_repair_equipment_scope())
    subject = f'[JustPlay] Báo hỏng thiết bị: {device.name}'
    message = f"""Hệ thống nhận yêu cầu hỗ trợ kỹ thuật mới:

- Thiết bị: {device.name}
- Model: {device.model_number or '—'}
- Serial: {device.serial_number or '—'}
- Vị trí: {_device_location(device)}
- Người báo: {reporter_name}
- Mô tả: {issue_description}

Yêu cầu #{service_request.pk}: {_request_url(service_request.pk)}
"""
    return _send(subject, message, recipients)


def notify_breakdown_from_request(service_request, *, reporter_name: str):
    """Gửi IT khi tạo Hỗ trợ kỹ thuật (có hoặc không liên kết thiết bị)."""
    device = service_request.equipment
    if device:
        return notify_it_new_breakdown(
            device=device,
            service_request=service_request,
            reporter_name=reporter_name,
            issue_description=service_request.description,
        )

    recipients = get_repair_notify_emails(service_request.effective_repair_equipment_scope())
    subject = f'[JustPlay] Hỗ trợ kỹ thuật: {service_request.title}'
    message = f"""Yêu cầu hỗ trợ kỹ thuật mới:

- Tiêu đề: {service_request.title}
- Người gửi: {reporter_name}
- Vị trí: {service_request.location_text or '—'}
- Thiết bị (text): {service_request.equipment_label or '—'}
- Mô tả: {service_request.description}

Chi tiết: {_request_url(service_request.pk)}
"""
    return _send(subject, message, recipients)


def notify_repair_completed(*, service_request, repair_note: str, repaired_by: str):
    """IT hoàn thành sửa — thông báo người gửi + email liên hệ thiết bị."""
    recipients = []
    requester = service_request.requester
    if requester.email:
        recipients.append(requester.email)

    device = service_request.equipment
    if device and device.contact_email:
        recipients.append(device.contact_email)

    recipients = _dedupe_emails(recipients)
    if not recipients:
        return False

    device_label = device.name if device else (service_request.equipment_label or 'Thiết bị')
    subject = f'[JustPlay] Đã xử lý xong: {device_label}'
    message = f"""Kính gửi Anh/Chị,

Thiết bị / yêu cầu đã được IT xử lý và đóng trên hệ thống.

- Yêu cầu: {service_request.title}
- Thiết bị: {device_label}
- Kỹ thuật viên: {repaired_by}
- Ghi chú: {repair_note or '—'}

Chi tiết: {_request_url(service_request.pk)}
"""
    return _send(subject, message, recipients)


def notify_repair_confirmed(*, service_request):
    """Người gửi xác nhận hoàn thành — thông báo IT (tuỳ chọn)."""
    recipients = get_it_notify_emails()
    device = service_request.equipment
    label = device.name if device else service_request.title
    subject = f'[JustPlay] Đã xác nhận sửa xong: {label}'
    message = f"""Người gửi đã xác nhận hoàn thành yêu cầu #{service_request.pk}.

- Thiết bị / tiêu đề: {label}
- Người xác nhận: {service_request.requester.get_full_name() or service_request.requester.username}

Chi tiết: {_request_url(service_request.pk)}
"""
    return _send(subject, message, recipients)
