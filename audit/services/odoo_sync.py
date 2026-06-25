"""Đồng bộ tài khoản Portal ↔ Odoo (XML-RPC)."""

from __future__ import annotations

import logging
import secrets
import ssl
import xmlrpc.client
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.models import User

from hrm.module_permissions import MODULE_ODOO, user_can_access_module, user_can_update_module

logger = logging.getLogger(__name__)


class OdooSyncError(Exception):
    pass


def odoo_configured() -> bool:
    return bool(
        (getattr(settings, 'ODOO_URL', '') or '').strip()
        and (getattr(settings, 'ODOO_DB', '') or '').strip()
        and (getattr(settings, 'ODOO_API_USER', '') or '').strip()
        and (getattr(settings, 'ODOO_API_PASSWORD', '') or '')
    )


def user_has_odoo_portal_access(user) -> bool:
    if not user or not user.is_authenticated or not user.is_active:
        return False
    profile = getattr(user, 'profile', None)
    if not profile or not profile.is_employed:
        return False
    return user_can_access_module(user, MODULE_ODOO)


def _odoo_public_url() -> str:
    return (getattr(settings, 'ODOO_PUBLIC_URL', '') or getattr(settings, 'ODOO_URL', '') or '').strip().rstrip('/')


def odoo_login_url(user) -> str:
    login = (user.email or user.username or '').strip()
    base = _odoo_public_url()
    if not base:
        return 'https://erp.justplay.vn/web/login'
    if login:
        return f'{base}/web/login?login={quote(login)}'
    return f'{base}/web/login'


def _xmlrpc_transport() -> xmlrpc.client.SafeTransport:
    if getattr(settings, 'ODOO_VERIFY_SSL', True):
        return xmlrpc.client.SafeTransport()
    transport = xmlrpc.client.SafeTransport(context=ssl._create_unverified_context())
    return transport


def _odoo_uid() -> int:
    url = settings.ODOO_URL.rstrip('/')
    transport = _xmlrpc_transport()
    common = xmlrpc.client.ServerProxy(
        f'{url}/xmlrpc/2/common',
        transport=transport,
        allow_none=True,
    )
    uid = common.authenticate(
        settings.ODOO_DB,
        settings.ODOO_API_USER,
        settings.ODOO_API_PASSWORD,
        {},
    )
    if not uid:
        raise OdooSyncError('Không đăng nhập được Odoo API (kiểm tra ODOO_API_USER/PASSWORD).')
    return int(uid)


def _odoo_models():
    url = settings.ODOO_URL.rstrip('/')
    transport = _xmlrpc_transport()
    return xmlrpc.client.ServerProxy(
        f'{url}/xmlrpc/2/object',
        transport=transport,
        allow_none=True,
    )


def _execute(model: str, method: str, *args, **kwargs):
    models = _odoo_models()
    return models.execute_kw(
        settings.ODOO_DB,
        _odoo_uid(),
        settings.ODOO_API_PASSWORD,
        model,
        method,
        list(args),
        kwargs,
    )


def _group_ids_for_user(user) -> list[int]:
    xml_ids = list(getattr(settings, 'ODOO_DEFAULT_GROUPS', []) or [])
    if user_can_update_module(user, MODULE_ODOO):
        xml_ids.extend(getattr(settings, 'ODOO_MANAGER_GROUPS', []) or [])
    if not xml_ids:
        xml_ids = ['base.group_user']
    seen: set[int] = set()
    ids: list[int] = []
    for xml_id in xml_ids:
        try:
            module, name = xml_id.split('.', 1)
            _model, gid = _execute('ir.model.data', 'check_object_reference', module, name)
            gid = int(gid)
        except Exception:
            logger.warning('Odoo group xml_id không tồn tại: %s', xml_id)
            continue
        if gid not in seen:
            seen.add(gid)
            ids.append(gid)
    if ids:
        return ids
    try:
        module, name = 'base.group_user'.split('.', 1)
        return [int(_execute('ir.model.data', 'check_object_reference', module, name)[1])]
    except Exception:
        return []


def _portal_display_name(user) -> str:
    profile = getattr(user, 'profile', None)
    if profile and profile.full_name:
        return profile.full_name.strip()
    return (user.get_full_name() or user.username or '').strip() or user.username


def _portal_login(user) -> str:
    return (user.username or '').strip() or (user.email or '').strip()


def _portal_email(user) -> str:
    return (user.email or '').strip() or f'{user.username}@justplay.local'


def _upsert_odoo_user_record(user, profile, *, password: str | None = None) -> dict:
    """Tạo/cập nhật res.users trên Odoo (không kiểm tra quyền menu Portal)."""
    login = _portal_login(user)
    if not login:
        return {'status': 'error', 'error': 'Thiếu username để đồng bộ Odoo.'}

    vals = {
        'name': _portal_display_name(user),
        'login': login,
        'email': _portal_email(user),
        'active': True,
    }
    group_ids = _group_ids_for_user(user)
    if group_ids:
        vals['groups_id'] = [(6, 0, group_ids)]

    created = False
    temp_password = None
    if profile.odoo_user_id:
        user_ids = _execute('res.users', 'search', [('id', '=', profile.odoo_user_id)], limit=1)
        if not user_ids:
            profile.odoo_user_id = None
            profile.save(update_fields=['odoo_user_id'])

    if profile.odoo_user_id:
        write_vals = dict(vals)
        if password:
            write_vals['password'] = password
        _execute('res.users', 'write', [profile.odoo_user_id], write_vals)
        odoo_id = profile.odoo_user_id
        if password:
            profile.odoo_password_synced = True
            profile.save(update_fields=['odoo_password_synced'])
    else:
        existing = _execute('res.users', 'search', [('login', '=', login)], limit=1)
        if existing:
            odoo_id = int(existing[0])
            write_vals = dict(vals)
            if password:
                write_vals['password'] = password
            _execute('res.users', 'write', [odoo_id], write_vals)
            if password:
                profile.odoo_password_synced = True
                profile.save(update_fields=['odoo_password_synced'])
        else:
            if password:
                vals['password'] = password
            else:
                temp_password = secrets.token_urlsafe(10)
                vals['password'] = temp_password
            odoo_id = int(_execute('res.users', 'create', vals))
            created = True
            profile.odoo_password_synced = bool(password)
        profile.odoo_user_id = odoo_id
        profile.save(update_fields=['odoo_user_id', 'odoo_password_synced'])

    result = {
        'status': 'ok',
        'odoo_user_id': odoo_id,
        'created': created,
        'login': login,
        'password_synced': bool(profile.odoo_password_synced),
    }
    if temp_password:
        result['temp_password'] = temp_password
    return result


def provision_erp_user(user, *, password: str | None = None) -> dict:
    """Tạo/cập nhật Odoo cho NV đang làm việc (bulk reset — không cần menu Odoo)."""
    if not isinstance(user, User):
        raise OdooSyncError('User không hợp lệ')

    profile = getattr(user, 'profile', None)
    if profile is None:
        return {'status': 'skipped', 'reason': 'no_profile'}
    if not profile.is_employed:
        return {'status': 'skipped', 'reason': 'not_employed'}
    if not odoo_configured():
        return {'status': 'skipped', 'reason': 'not_configured'}

    try:
        return _upsert_odoo_user_record(user, profile, password=password)
    except OdooSyncError:
        raise
    except Exception as exc:
        logger.exception('Odoo provision failed for user %s', user.pk)
        raise OdooSyncError(str(exc)) from exc


def sync_user_to_odoo(user, *, password: str | None = None) -> dict:
    """Tạo/cập nhật/vô hiệu hóa res.users trên Odoo theo quyền menu Odoo trên Portal."""
    if not isinstance(user, User):
        raise OdooSyncError('User không hợp lệ')

    profile = getattr(user, 'profile', None)
    if profile is None:
        return {'status': 'skipped', 'reason': 'no_profile'}

    if not odoo_configured():
        return {'status': 'skipped', 'reason': 'not_configured'}

    should_sync = user_has_odoo_portal_access(user)

    try:
        if not should_sync:
            if profile.odoo_user_id:
                _execute('res.users', 'write', [profile.odoo_user_id], {'active': False})
                profile.odoo_user_id = None
                profile.save(update_fields=['odoo_user_id'])
            return {'status': 'deactivated'}

        login = _portal_login(user)
        if not login:
            return {'status': 'error', 'error': 'Thiếu username để đồng bộ Odoo.'}

        return _upsert_odoo_user_record(user, profile, password=password)
    except OdooSyncError:
        raise
    except Exception as exc:
        logger.exception('Odoo sync failed for user %s', user.pk)
        raise OdooSyncError(str(exc)) from exc


def ensure_portal_user_in_odoo(user, *, password: str | None = None) -> dict:
    try:
        return sync_user_to_odoo(user, password=password)
    except OdooSyncError as exc:
        return {'status': 'error', 'error': str(exc)}


def notify_portal_password_changed(user, raw_password: str) -> None:
    if not raw_password or not user_has_odoo_portal_access(user):
        return
    if not odoo_configured():
        return
    try:
        sync_user_to_odoo(user, password=raw_password)
    except OdooSyncError:
        logger.exception('Không đồng bộ mật khẩu Odoo cho user %s', user.pk)


def sync_all_odoo_users(*, password_reset: bool = False) -> dict:
    if not odoo_configured():
        raise OdooSyncError('Chưa cấu hình Odoo API.')

    stats = {'ok': 0, 'deactivated': 0, 'skipped': 0, 'errors': []}
    users = User.objects.filter(is_active=True).select_related('profile')
    for user in users:
        try:
            if user_has_odoo_portal_access(user):
                sync_user_to_odoo(user)
                stats['ok'] += 1
            elif getattr(user, 'profile', None) and user.profile.odoo_user_id:
                sync_user_to_odoo(user)
                stats['deactivated'] += 1
            else:
                stats['skipped'] += 1
        except OdooSyncError as exc:
            stats['errors'].append(f'{user.username}: {exc}')
    return stats
