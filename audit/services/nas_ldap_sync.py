"""Đồng bộ tài khoản Portal ↔ Synology Directory Server (LDAP)."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import User

from nas_storage.dept_nas_config import (
    DEPARTMENT_NAS_GROUPS,
    nas_group_for_portal_department,
)

logger = logging.getLogger(__name__)

GROUP_OBJECT_CLASSES = ['top', 'posixGroup']
USER_OBJECT_CLASSES = [
    'top',
    'person',
    'organizationalPerson',
    'inetOrgPerson',
    'posixAccount',
]

DEPARTMENT_LDAP_GROUPS = DEPARTMENT_NAS_GROUPS
DEFAULT_LDAP_GROUP = 'users'


class NasLdapSyncError(Exception):
    pass


def nas_ldap_sync_enabled() -> bool:
    return bool(getattr(settings, 'NAS_LDAP_SYNC_ENABLED', False))


def _skip_usernames() -> frozenset[str]:
    raw = getattr(settings, 'NAS_LDAP_SYNC_SKIP_USERNAMES', 'admin,ductn,vuonglnt')
    if isinstance(raw, (list, tuple, frozenset, set)):
        items = raw
    else:
        items = str(raw or '').split(',')
    return frozenset(x.strip().lower() for x in items if str(x).strip())


def nas_ldap_configured() -> bool:
    if not nas_ldap_sync_enabled():
        return False
    return bool(
        (_ldap_host() or '').strip()
        and (_ldap_base_dn() or '').strip()
        and (_ldap_bind_dn() or '').strip()
        and _ldap_bind_password()
    )


def _ldap_host() -> str:
    explicit = (getattr(settings, 'NAS_LDAP_HOST', '') or '').strip()
    if explicit:
        return explicit
    dsm_url = (getattr(settings, 'NAS_DSM_URL', '') or '').strip()
    if dsm_url:
        host = urlparse(dsm_url).hostname
        if host:
            return host
    return ''


def _ldap_port() -> int:
    return int(getattr(settings, 'NAS_LDAP_PORT', 636) or 636)


def _ldap_use_ssl() -> bool:
    return bool(getattr(settings, 'NAS_LDAP_USE_SSL', True))


def _ldap_verify_ssl() -> bool:
    return bool(getattr(settings, 'NAS_LDAP_VERIFY_SSL', False))


def _ldap_base_dn() -> str:
    return (getattr(settings, 'NAS_LDAP_BASE_DN', 'dc=ldap,dc=justplay,dc=local') or '').strip()


def _ldap_bind_dn() -> str:
    return (
        getattr(settings, 'NAS_LDAP_BIND_DN', 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local') or ''
    ).strip()


def _ldap_bind_password() -> str:
    pw = (getattr(settings, 'NAS_LDAP_BIND_PASSWORD', '') or '').strip()
    if pw:
        return pw
    return (getattr(settings, 'NAS_DSM_PASSWORD', '') or '').strip()


def _groups_dn() -> str:
    return f'cn=groups,{_ldap_base_dn()}'


def _users_dn() -> str:
    return f'cn=users,{_ldap_base_dn()}'


def _group_dn(name: str) -> str:
    return f'cn={name},{_groups_dn()}'


def _user_dn(uid: str) -> str:
    return f'uid={uid},{_users_dn()}'


def nas_ldap_group_for_department(department_name: str | None) -> str | None:
    return nas_group_for_portal_department(department_name)


def _portal_login(user: User) -> str:
    return (user.username or '').strip()


def _portal_email(user: User) -> str:
    return (user.email or '').strip() or f'{user.username}@justplay.local'


def _portal_display_name(user: User) -> str:
    profile = getattr(user, 'profile', None)
    if profile and profile.full_name:
        return profile.full_name.strip()
    return (user.get_full_name() or user.username or '').strip() or user.username


def _sn_from_name(display_name: str, fallback: str) -> str:
    parts = [p for p in re.split(r'\s+', (display_name or '').strip()) if p]
    return parts[-1] if parts else fallback


def _should_sync_user(user: User) -> bool:
    if not user or not user.is_active:
        return False
    login = _portal_login(user)
    if not login:
        return False
    if login.lower() in _skip_usernames():
        return False
    profile = getattr(user, 'profile', None)
    if profile is None or not profile.is_employed:
        return False
    return True


@contextmanager
def _ldap_connection():
    if not nas_ldap_configured():
        raise NasLdapSyncError('Chưa cấu hình NAS LDAP (NAS_LDAP_SYNC_ENABLED và bind DN/password).')

    try:
        import ssl

        from ldap3 import Connection, Server, Tls
    except ImportError as exc:
        raise NasLdapSyncError('Thiếu package ldap3 — cài requirements.txt trên server.') from exc

    tls = None
    if _ldap_use_ssl():
        tls = Tls(validate=ssl.CERT_REQUIRED if _ldap_verify_ssl() else ssl.CERT_NONE)

    server = Server(
        _ldap_host(),
        port=_ldap_port(),
        use_ssl=_ldap_use_ssl(),
        tls=tls,
    )
    conn = Connection(
        server,
        user=_ldap_bind_dn(),
        password=_ldap_bind_password(),
        auto_bind=True,
        raise_exceptions=True,
    )
    try:
        yield conn
    finally:
        conn.unbind()


def _next_gid_number(conn) -> int:
    from ldap3 import SUBTREE

    conn.search(_groups_dn(), '(objectClass=posixGroup)', search_scope=SUBTREE, attributes=['gidNumber'])
    values = []
    for entry in conn.entries:
        if hasattr(entry, 'gidNumber') and entry.gidNumber.value is not None:
            values.append(int(entry.gidNumber.value))
    return max(values or [1_000_000]) + 1


def _next_uid_number(conn) -> int:
    from ldap3 import SUBTREE

    conn.search(_users_dn(), '(objectClass=posixAccount)', search_scope=SUBTREE, attributes=['uidNumber'])
    values = []
    for entry in conn.entries:
        if hasattr(entry, 'uidNumber') and entry.uidNumber.value is not None:
            values.append(int(entry.uidNumber.value))
    return max(values or [2_000]) + 1


def primary_ldap_group_for_department(department_group: str | None) -> str:
    """Primary group (gidNumber) — NAS DSM hiển thị group chính theo gidNumber, không chỉ memberUid."""
    if department_group in DEPARTMENT_LDAP_GROUPS:
        return department_group
    return DEFAULT_LDAP_GROUP


def _group_gid(conn, group_name: str) -> int:
    from ldap3 import SUBTREE

    conn.search(_groups_dn(), f'(cn={group_name})', search_scope=SUBTREE, attributes=['gidNumber'])
    if not conn.entries:
        raise NasLdapSyncError(f'Không tìm thấy group LDAP "{group_name}".')
    return int(conn.entries[0].gidNumber.value)


def _users_group_gid(conn) -> int:
    return _group_gid(conn, DEFAULT_LDAP_GROUP)


def _group_exists(conn, name: str) -> bool:
    from ldap3 import SUBTREE

    conn.search(_groups_dn(), f'(cn={name})', search_scope=SUBTREE, attributes=['cn'])
    return bool(conn.entries)


def _user_exists(conn, uid: str) -> bool:
    from ldap3 import SUBTREE

    conn.search(_users_dn(), f'(uid={uid})', search_scope=SUBTREE, attributes=['uid'])
    return bool(conn.entries)


def _ensure_group(conn, name: str, *, description: str = '') -> str:
    dn = _group_dn(name)
    if _group_exists(conn, name):
        return dn

    gid = _next_gid_number(conn)
    attrs = {'cn': name, 'gidNumber': gid}
    if description:
        attrs['description'] = description
    conn.add(dn, GROUP_OBJECT_CLASSES, attrs)
    if conn.result['result'] != 0:
        raise NasLdapSyncError(f'Không tạo được group LDAP {name}: {conn.result}')
    return dn


def _ensure_department_groups_on_conn(conn) -> list[str]:
    from ldap3 import SUBTREE

    created: list[str] = []
    _ensure_group(conn, DEFAULT_LDAP_GROUP)
    for group_name in sorted(DEPARTMENT_LDAP_GROUPS):
        existed = _group_exists(conn, group_name)
        _ensure_group(conn, group_name, description=f'Phòng ban {group_name}')
        if not existed:
            created.append(group_name)
    return created


def ensure_department_groups() -> list[str]:
    """Tạo group phòng ban trên LDAP nếu chưa có."""
    with _ldap_connection() as conn:
        return _ensure_department_groups_on_conn(conn)


def _set_member_uid(conn, group_name: str, uid: str, *, add: bool) -> None:
    from ldap3 import MODIFY_ADD, MODIFY_DELETE, SUBTREE

    if not _group_exists(conn, group_name):
        return
    dn = _group_dn(group_name)
    conn.search(dn, '(objectClass=posixGroup)', search_scope=SUBTREE, attributes=['memberUid'])
    if not conn.entries:
        return
    current = set(conn.entries[0].memberUid.values if hasattr(conn.entries[0], 'memberUid') else [])
    if add and uid in current:
        return
    if not add and uid not in current:
        return
    operation = MODIFY_ADD if add else MODIFY_DELETE
    conn.modify(dn, {'memberUid': [(operation, [uid])]})
    if conn.result['result'] not in (0, 68):
        raise NasLdapSyncError(
            f'Không cập nhật memberUid group {group_name} cho {uid}: {conn.result}'
        )


def _sync_group_membership(conn, uid: str, department_group: str | None) -> None:
    _set_member_uid(conn, DEFAULT_LDAP_GROUP, uid, add=True)
    target = department_group if department_group in DEPARTMENT_LDAP_GROUPS else None
    for group_name in DEPARTMENT_LDAP_GROUPS:
        _set_member_uid(conn, group_name, uid, add=(group_name == target))


def _upsert_ldap_user(
    conn,
    user: User,
    *,
    password: str | None = None,
) -> dict:
    from ldap3 import MODIFY_REPLACE, SUBTREE

    uid = _portal_login(user)
    display_name = _portal_display_name(user)
    sn = _sn_from_name(display_name, uid)
    email = _portal_email(user)
    dept_name = None
    profile = getattr(user, 'profile', None)
    if profile and profile.department_id:
        dept_name = getattr(profile.department, 'name', None)
    department_group = nas_ldap_group_for_department(dept_name)
    primary_group = primary_ldap_group_for_department(department_group)
    gid_number = _group_gid(conn, primary_group)

    user_dn = _user_dn(uid)
    created = not _user_exists(conn, uid)

    if created:
        uid_number = _next_uid_number(conn)
        attrs = {
            'uid': uid,
            'cn': display_name,
            'sn': sn,
            'mail': email,
            'displayName': display_name,
            'gecos': display_name,
            'uidNumber': uid_number,
            'gidNumber': gid_number,
            'homeDirectory': f'/home/{uid}',
            'loginShell': '/sbin/nologin',
            'userPassword': password or _ldap_bind_password(),
        }
        conn.add(user_dn, USER_OBJECT_CLASSES, attrs)
        if conn.result['result'] != 0:
            raise NasLdapSyncError(f'Không tạo LDAP user {uid}: {conn.result}')
    else:
        changes = {
            'cn': [(MODIFY_REPLACE, [display_name])],
            'sn': [(MODIFY_REPLACE, [sn])],
            'mail': [(MODIFY_REPLACE, [email])],
            'displayName': [(MODIFY_REPLACE, [display_name])],
            'gecos': [(MODIFY_REPLACE, [display_name])],
            'gidNumber': [(MODIFY_REPLACE, [gid_number])],
        }
        if password:
            changes['userPassword'] = [(MODIFY_REPLACE, [password])]
        conn.modify(user_dn, changes)
        if conn.result['result'] != 0:
            raise NasLdapSyncError(f'Không cập nhật LDAP user {uid}: {conn.result}')

    _sync_group_membership(conn, uid, department_group)
    return {
        'status': 'ok',
        'uid': uid,
        'dn': user_dn,
        'created': created,
        'department_group': department_group,
        'primary_group': primary_group,
        'password_synced': bool(password),
    }


def _reload_user_for_ldap_sync(user: User) -> User:
    return (
        User.objects.select_related('profile', 'profile__department')
        .get(pk=user.pk)
    )


def provision_ldap_user(user: User, *, password: str | None = None) -> dict:
    if not isinstance(user, User):
        raise NasLdapSyncError('User không hợp lệ')
    if not nas_ldap_configured():
        return {'status': 'skipped', 'reason': 'not_configured'}

    user = _reload_user_for_ldap_sync(user)
    if not _should_sync_user(user):
        return {'status': 'skipped', 'reason': 'not_eligible'}

    try:
        with _ldap_connection() as conn:
            groups_created = _ensure_department_groups_on_conn(conn)
            result = _upsert_ldap_user(conn, user, password=password)
            if groups_created:
                result['groups_created'] = groups_created
            return result
    except NasLdapSyncError:
        raise
    except Exception as exc:
        if exc.__class__.__name__ == 'LDAPException':
            logger.exception('NAS LDAP provision failed for user %s', user.pk)
            raise NasLdapSyncError(str(exc)) from exc
        raise


def notify_portal_password_changed(user: User, raw_password: str) -> None:
    if not raw_password or not _should_sync_user(user):
        return
    if not nas_ldap_configured():
        return
    try:
        provision_ldap_user(user, password=raw_password)
    except NasLdapSyncError:
        logger.exception('Không đồng bộ mật khẩu NAS LDAP cho user %s', user.pk)


def ensure_portal_user_in_ldap(user: User, *, password: str | None = None) -> dict:
    """Đồng bộ user/group phòng ban LDAP (khi sửa phòng ban hoặc tạo NV)."""
    try:
        return provision_ldap_user(user, password=password)
    except NasLdapSyncError as exc:
        return {'status': 'error', 'error': str(exc)}


def notify_ldap_profile_changed(user: User) -> None:
    if not nas_ldap_configured():
        return
    try:
        provision_ldap_user(user, password=None)
    except NasLdapSyncError:
        logger.exception('Không đồng bộ profile NAS LDAP cho user %s', user.pk)


def sync_all_nas_ldap_users(*, password: str | None = None) -> dict:
    if not nas_ldap_configured():
        raise NasLdapSyncError('Chưa cấu hình NAS LDAP.')

    stats = {'ok': 0, 'skipped': 0, 'errors': [], 'groups_created': []}
    with _ldap_connection() as conn:
        stats['groups_created'] = _ensure_department_groups_on_conn(conn)

        users = (
            User.objects.filter(is_active=True)
            .select_related('profile', 'profile__department')
            .order_by('username')
        )
        for user in users:
            if not _should_sync_user(user):
                stats['skipped'] += 1
                continue
            try:
                _upsert_ldap_user(conn, user, password=password)
                stats['ok'] += 1
            except NasLdapSyncError as exc:
                stats['errors'].append(f'{user.username}: {exc}')
            except Exception as exc:
                if exc.__class__.__name__ != 'LDAPException':
                    raise
                stats['errors'].append(f'{user.username}: {exc}')
    return stats
