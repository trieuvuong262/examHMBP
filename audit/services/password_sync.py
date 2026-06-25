"""Đồng bộ mật khẩu Portal sang hệ thống ngoài (Odoo, NAS LDAP)."""

from __future__ import annotations

from django.contrib.auth.models import User

from audit.services.nas_ldap_sync import (
    notify_ldap_profile_changed,
    notify_portal_password_changed as notify_nas_ldap_password_changed,
)
from audit.services.odoo_sync import notify_portal_password_changed as notify_odoo_password_changed


def notify_external_password_changed(user: User, raw_password: str) -> None:
    notify_odoo_password_changed(user, raw_password)
    notify_nas_ldap_password_changed(user, raw_password)


def notify_external_profile_changed(user: User) -> None:
    """Đồng bộ thay đổi phòng ban / profile sang LDAP (group NAS)."""
    notify_ldap_profile_changed(user)
