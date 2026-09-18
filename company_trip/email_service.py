"""Gửi email Company Trip qua SMTP portal."""

from __future__ import annotations

import logging

from django.template import Context, Template
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags

from audit.email_smtp import email_is_configured, send_portal_mail
from company_trip.models import TripEmailTemplate, TripSettings

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


def build_email_context(fullname: str, gender: str = '', request=None, **extra) -> dict:
    settings_obj = TripSettings.load()
    return {
        'fullname': fullname or '',
        'gender_prefix': _gender_prefix(gender),
        'dates': settings_obj.dates_display,
        'destination': settings_obj.destination,
        'title': settings_obj.title,
        'register_url': _absolute_register_url(request),
        **extra,
    }


def render_trip_email(fullname: str, gender: str = '', request=None, **extra) -> tuple[str, str, str]:
    tpl = TripEmailTemplate.load()
    ctx = build_email_context(fullname, gender, request=request, **extra)
    subject = Template(tpl.subject).render(Context(ctx))
    body_html = Template(tpl.body).render(Context(ctx))
    # Wrap in portal shell if bare
    if '<html' not in body_html.lower():
        body_html = render_to_string(
            'company_trip/email_wrap.html',
            {'body_html': body_html, **ctx},
        )
    plain = strip_tags(body_html)
    return subject, plain, body_html


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
