"""Gửi email Company Trip qua SMTP portal."""

from __future__ import annotations

import logging

from django.template import Context, Template
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from audit.email_smtp import email_is_configured, send_portal_mail
from company_trip.constants import ROOM_COLLEAGUE, ROOM_RELATIVE
from company_trip.models import TripEmailTemplate, TripSettings

INVITE_SUBJECT = 'Thư mời tham gia Kế hoạch du lịch nghỉ mát 2026 - Just Play'

logger = logging.getLogger(__name__)


def _gender_prefix(gender: str) -> str:
    g = (gender or '').upper()
    if g in ('M', 'NAM', 'MALE'):
        return 'Anh'
    if g in ('F', 'NỮ', 'NU', 'FEMALE'):
        return 'Chị'
    return 'Anh/Chị'


def _absolute_register_url(request=None) -> str:
    path = reverse('company_trip:register')
    if request is not None:
        return request.build_absolute_uri(path)
    from django.conf import settings
    base = (getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '') or '').rstrip('/')
    return f'{base}{path}' if base else path


def _companions_text(value) -> str:
    if isinstance(value, (list, tuple)):
        names = [str(name).strip() for name in value if str(name).strip()]
    else:
        names = [part.strip() for part in str(value or '').split(',') if part.strip()]
    return ', '.join(name.upper() for name in names)


def build_email_context(fullname: str, gender: str = '', request=None, **extra) -> dict:
    settings_obj = TripSettings.load()
    extra = dict(extra)
    companions = _companions_text(extra.pop('companions', ''))
    ctx = {
        'fullname': (fullname or '').strip().upper(),
        'gender_prefix': _gender_prefix(gender),
        'dates': settings_obj.dates_display,
        'destination': settings_obj.destination,
        'title': settings_obj.title,
        'year': '2026',
        'location': 'Ninh Thuận – Vịnh Vĩnh Hy',
        'resort': 'TTC Resort',
        'pickup': 'Xưởng Just Play – 19 Chiến Lược, Bình Trị Đông',
        'gather_time': 'Trước 02 giờ, ngày 22/11/2026',
        'register_url': _absolute_register_url(request),
        'itinerary': mark_safe(render_to_string('company_trip/includes/itinerary_email.html')),
        'room_type': '',
        'companions': companions,
        'phone': '',
        'department': '',
    }
    ctx.update(extra)
    return ctx


def render_trip_message(fullname: str, gender: str = '', request=None, **extra) -> tuple[str, str]:
    """Tiêu đề và nội dung HTML theo mẫu đang lưu, chưa bọc khung email."""
    tpl = TripEmailTemplate.load()
    ctx = build_email_context(fullname, gender, request=request, **extra)
    subject = Template(tpl.subject).render(Context(ctx))
    body_html = Template(tpl.body).render(Context(ctx))
    return subject, body_html


def render_trip_email(fullname: str, gender: str = '', request=None, **extra) -> tuple[str, str, str]:
    subject, body_html = render_trip_message(fullname, gender, request=request, **extra)
    if '<html' not in body_html.lower():
        ctx = build_email_context(fullname, gender, request=request, **extra)
        body_html = render_to_string(
            'company_trip/email_wrap.html',
            {'body_html': body_html, 'title': subject, **ctx},
        )
    plain = strip_tags(body_html)
    return subject, plain, body_html


def _display_name(name: str) -> str:
    return (name or '').strip().upper()


def _profile_email(profile) -> str:
    if not profile:
        return ''
    user = getattr(profile, 'user', None)
    return ((getattr(user, 'email', '') or '')).strip()


def send_invite_letter(
    to_email: str,
    full_name: str,
    gender: str = '',
    pickup: str = '',
    room_type: str = '',
    companions: list[str] | None = None,
    request=None,
) -> bool:
    """Thư mời sau khi đăng ký. Xưng hô Anh/Chị theo giới tính người nhận."""
    if not (to_email or '').strip():
        return False
    if not email_is_configured():
        logger.warning('Company Trip email skipped — SMTP chưa cấu hình')
        return False
    settings_obj = TripSettings.load()
    prefix = _gender_prefix(gender)
    ctx = {
        'title': INVITE_SUBJECT,
        'gender_prefix': prefix,
        'fullname': _display_name(full_name),
        'pickup': (pickup or '').strip() or '—',
        'dates': settings_obj.dates_display,
        'destination': settings_obj.destination,
        'room_type': (room_type or '').strip() or '—',
        'companions': [_display_name(name) for name in (companions or []) if (name or '').strip()],
    }
    body_html = render_to_string('company_trip/invite_email.html', ctx)
    html = render_to_string('company_trip/email_wrap.html', {'body_html': body_html, **ctx})
    plain = strip_tags(html)
    try:
        send_portal_mail(INVITE_SUBJECT, plain, [to_email.strip()], html_message=html)
        return True
    except Exception:
        logger.exception('Gửi thư mời Company Trip thất bại tới %s', to_email)
        return False


def _companion_names_for(reg, *, recipient: str) -> list[str]:
    """recipient: owner | colleague."""
    if reg.room_type == ROOM_COLLEAGUE:
        if recipient == 'owner':
            return [reg.companion1_name] if reg.companion1_name else []
        return [reg.full_name] if reg.full_name else []
    if reg.room_type == ROOM_RELATIVE and recipient == 'owner' and reg.relative_full_name:
        return [reg.relative_full_name]
    return []


def _send_saved_template(
    to_email: str,
    full_name: str,
    gender: str,
    reg,
    companions,
    request=None,
    phone: str = '',
    department: str = '',
) -> bool:
    """Một thư theo mẫu đang lưu trên trang Email, gửi từ it@justplay.vn."""
    extra = {
        'room_type': reg.room_type or '',
        'companions': companions,
        'phone': phone or '',
        'department': department or '',
    }
    if (reg.pickup_point or '').strip():
        extra['pickup'] = reg.pickup_point
    return send_trip_email(
        to_email,
        full_name,
        gender,
        request=request,
        **extra,
    )


def send_registration_invites(reg, request=None) -> int:
    """Gửi đúng một lượt theo mẫu Email.

    Đồng nghiệp: tới email của cả hai nhân viên (nếu đồng nghiệp đã có email).
    Người thân hoặc ban tổ chức tự sắp xếp: chỉ người đăng ký.
    """
    sent_to: set[str] = set()

    def deliver(email, name, gender, companions, phone='', department='') -> bool:
        key = (email or '').strip().lower()
        if not key or key in sent_to:
            return False
        ok = _send_saved_template(
            email, name, gender, reg, companions,
            request=request, phone=phone, department=department,
        )
        if ok:
            sent_to.add(key)
        return ok

    sent = 0
    if deliver(
        reg.email,
        reg.full_name,
        reg.gender,
        _companion_names_for(reg, recipient='owner'),
        phone=reg.phone or '',
        department=reg.department_name or '',
    ):
        sent += 1

    if reg.room_type != ROOM_COLLEAGUE or not reg.companion1_id:
        return sent

    colleague = reg.companion1
    email = _profile_email(colleague)
    if not email or email.lower() == (reg.companion_email or '').strip().lower():
        return sent
    department = ''
    if getattr(colleague, 'department_id', None):
        department = colleague.department.name if colleague.department_id else ''
    if deliver(
        email,
        reg.companion1_name or colleague.full_name,
        colleague.gender,
        _companion_names_for(reg, recipient='colleague'),
        phone=getattr(colleague, 'phone', '') or '',
        department=department,
    ):
        reg.companion_email = email
        reg.save(update_fields=['companion_email', 'updated_at'])
        sent += 1
    return sent


def send_companion_invite(reg, to_email: str, request=None) -> bool:
    """Gửi một lần cho đồng nghiệp khi xác nhận, nếu lúc đăng ký chưa gửi được."""
    key = (to_email or '').strip().lower()
    if not key or key == (reg.email or '').strip().lower():
        return False
    colleague = reg.companion1
    department = ''
    phone = ''
    gender = ''
    name = reg.companion1_name
    if colleague is not None:
        gender = colleague.gender or ''
        phone = colleague.phone or ''
        name = name or colleague.full_name
        if colleague.department_id:
            department = colleague.department.name
    ok = _send_saved_template(
        to_email,
        name,
        gender,
        reg,
        _companion_names_for(reg, recipient='colleague'),
        request=request,
        phone=phone,
        department=department,
    )
    if ok and key != (reg.email or '').strip().lower():
        reg.companion_email = to_email.strip()
        reg.save(update_fields=['companion_email', 'updated_at'])
    return ok


def send_trip_email(to_email: str, fullname: str, gender: str = '', request=None, **extra) -> bool:
    if not (to_email or '').strip():
        return False
    if not email_is_configured():
        logger.warning('Company Trip email skipped — SMTP chưa cấu hình')
        return False
    try:
        subject, plain, html = render_trip_email(fullname, gender, request=request, **extra)
        send_portal_mail(subject, plain, [to_email.strip()], html_message=html)
        return True
    except Exception:
        logger.exception('Gửi email Company Trip thất bại tới %s', to_email)
        return False
