"""Gửi mail Portal — ưu tiên SMTP lưu trên trang Quản trị, fallback .env."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import get_connection, send_mail

logger = logging.getLogger(__name__)


def get_smtp_config():
    from audit.models import EmailSmtpConfig

    return EmailSmtpConfig.get_solo()


def email_is_configured() -> bool:
    """DB bật + đủ host/from, hoặc .env SMTP/console (dev)."""
    try:
        cfg = get_smtp_config()
        if cfg.is_ready():
            return True
    except Exception:
        pass

    backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').strip()
    if 'console' in backend or 'locmem' in backend or 'dummy' in backend:
        return True
    return bool((getattr(settings, 'EMAIL_HOST', '') or '').strip())


def get_from_email() -> str:
    try:
        cfg = get_smtp_config()
        if cfg.is_ready() and (cfg.from_email or '').strip():
            return cfg.from_email.strip()
    except Exception:
        pass
    return (getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@portal.justplay.vn').strip()


def get_mail_connection():
    """Connection SMTP từ DB nếu sẵn sàng; ngược lại backend mặc định Django."""
    try:
        cfg = get_smtp_config()
    except Exception:
        cfg = None

    if cfg and cfg.is_ready():
        return get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=(cfg.host or '').strip(),
            port=int(cfg.port or 587),
            username=(cfg.username or '').strip() or None,
            password=cfg.password or None,
            use_tls=bool(cfg.use_tls),
            use_ssl=bool(cfg.use_ssl),
            fail_silently=False,
        )
    return get_connection(fail_silently=False)


def send_portal_mail(
    subject: str,
    message: str,
    recipient_list: list[str],
    *,
    html_message: str | None = None,
    fail_silently: bool = False,
) -> int:
    if not email_is_configured():
        raise RuntimeError('Email chưa cấu hình (SMTP trên Quản trị hệ thống hoặc .env).')
    connection = get_mail_connection()
    return send_mail(
        subject,
        message,
        get_from_email(),
        recipient_list,
        fail_silently=fail_silently,
        html_message=html_message,
        connection=connection,
    )


def smtp_status_dict() -> dict[str, Any]:
    cfg = get_smtp_config()
    env_host = (getattr(settings, 'EMAIL_HOST', '') or '').strip()
    env_backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').strip()
    env_has_password = bool((getattr(settings, 'EMAIL_HOST_PASSWORD', '') or '').strip())
    return {
        'db_enabled': cfg.enabled,
        'db_ready': cfg.is_ready(),
        'db_host': (cfg.host or '').strip() or '—',
        'db_port': cfg.port,
        'db_username': (cfg.username or '').strip() or '—',
        'db_has_password': bool((cfg.password or '').strip()),
        'db_use_tls': cfg.use_tls,
        'db_use_ssl': cfg.use_ssl,
        'db_from_email': (cfg.from_email or '').strip() or '—',
        'db_updated_at': cfg.updated_at,
        'active_source': 'db' if cfg.is_ready() else ('env' if env_host or 'console' in env_backend else 'none'),
        'env_backend': env_backend or '—',
        'env_host': env_host or '—',
        'env_port': getattr(settings, 'EMAIL_PORT', 587),
        'env_user': (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip() or '—',
        'env_has_password': env_has_password,
        'env_from': (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip() or '—',
        'env_use_tls': bool(getattr(settings, 'EMAIL_USE_TLS', True)),
        'configured': email_is_configured(),
    }
