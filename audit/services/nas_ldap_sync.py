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
    'sambaSamAccount',
    'sambaIdmapEntry',
]

DEPARTMENT_LDAP_GROUPS = DEPARTMENT_NAS_GROUPS
DEFAULT_LDAP_GROUP = 'users'


class NasLdapSyncError(Exception):
    pass


def nas_ldap_sync_enabled() -> bool:
    return bool(getattr(settings, 'NAS_LDAP_SYNC_ENABLED', False))


def _skip_usernames() -> frozenset[str]:
    raw = getattr(settings, 'NAS_LDAP_SYNC_SKIP_USERNAMES', 'admin,ductn')
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


def _portal_ldap_group_names(user: User) -> set[str]:
    """
    Nhóm LDAP theo quyền NAS Portal: map phòng ban + portal_members,
    trừ portal_excluded_members (cùng logic user_nas_access_groups).
    """
    from nas_storage.portal_access import user_nas_access_groups

    names = set(user_nas_access_groups(user).values_list('name', flat=True))
    return {name for name in names if name in DEPARTMENT_LDAP_GROUPS}


def _primary_ldap_group_for_user(user: User, department_group: str | None) -> str:
    """Primary gidNumber: ưu tiên nhóm browse_all (vd. TGD), rồi phòng ban."""
    from nas_storage.portal_access import user_nas_access_groups

    browse_all = (
        user_nas_access_groups(user)
        .filter(portal_browse_all=True, name__in=DEPARTMENT_LDAP_GROUPS)
        .order_by('name')
        .values_list('name', flat=True)
        .first()
    )
    if browse_all:
        return browse_all
    return primary_ldap_group_for_department(department_group)


def _sync_group_membership(conn, uid: str, ldap_groups: set[str] | None) -> None:
    _set_member_uid(conn, DEFAULT_LDAP_GROUP, uid, add=True)
    targets = {g for g in (ldap_groups or set()) if g in DEPARTMENT_LDAP_GROUPS}
    for group_name in DEPARTMENT_LDAP_GROUPS:
        _set_member_uid(conn, group_name, uid, add=(group_name in targets))


def _read_domain_sid(conn) -> str:
    from ldap3 import SUBTREE

    conn.search(_ldap_base_dn(), '(objectClass=sambaDomain)', search_scope=SUBTREE, attributes=['sambaSID'])
    if not conn.entries:
        raise NasLdapSyncError('Không tìm thấy sambaDomain trên LDAP.')
    sid = conn.entries[0].sambaSID.value
    return str(sid[0] if isinstance(sid, list) else sid)


def _ldap_password_hash(raw_password: str) -> str:
    import subprocess

    hashed = subprocess.check_output(['openssl', 'passwd', '-6', raw_password], text=True).strip()
    if not hashed.startswith('$6$'):
        raise NasLdapSyncError('Không hash được mật khẩu LDAP (openssl passwd).')
    return '{CRYPT}' + hashed


def _samba_nt_password(raw_password: str) -> str:
    from passlib.hash import nthash as nthash_algo

    return nthash_algo.hash(raw_password).upper()


def _next_samba_rid(conn) -> int:
    from ldap3 import SUBTREE

    conn.search(_users_dn(), '(sambaSID=*)', search_scope=SUBTREE, attributes=['sambaSID'])
    rids: list[int] = []
    for entry in conn.entries:
        sid = entry.sambaSID.value
        raw = str(sid[0] if isinstance(sid, list) else sid)
        rids.append(int(raw.rsplit('-', 1)[-1]))
    return max(rids or [1004]) + 1


def _samba_account_attrs(*, rid: int, password: str, domain_sid: str) -> dict:
    import time

    return {
        'sambaSID': f'{domain_sid}-{rid}',
        'sambaNTPassword': _samba_nt_password(password),
        'sambaLMPassword': 'X' * 32,
        'sambaAcctFlags': '[U          ]',
        'sambaPwdLastSet': int(time.time()),
        'sambaPasswordHistory': '0' * 64,
    }


def _user_uid_number(conn, uid: str) -> int:
    from ldap3 import SUBTREE

    conn.search(_users_dn(), f'(uid={uid})', search_scope=SUBTREE, attributes=['uidNumber'])
    if not conn.entries:
        raise NasLdapSyncError(f'Không tìm thấy uidNumber cho {uid}.')
    return int(conn.entries[0].uidNumber.value)


def _user_has_samba_account(conn, uid: str) -> bool:
    from ldap3 import SUBTREE

    conn.search(_user_dn(uid), '(objectClass=sambaSamAccount)', search_scope=SUBTREE, attributes=['uid'])
    return bool(conn.entries)


def _apply_samba_account(conn, *, uid: str, password: str, rid: int | None = None) -> None:
    from ldap3 import MODIFY_ADD, MODIFY_REPLACE

    domain_sid = _read_domain_sid(conn)
    if rid is None:
        if _user_has_samba_account(conn, uid):
            conn.search(_user_dn(uid), '(sambaSID=*)', attributes=['sambaSID'])
            sid = conn.entries[0].sambaSID.value
            raw = str(sid[0] if isinstance(sid, list) else sid)
            rid = int(raw.rsplit('-', 1)[-1])
        else:
            rid = _next_samba_rid(conn)
    samba_attrs = _samba_account_attrs(rid=rid, password=password, domain_sid=domain_sid)
    user_dn = _user_dn(uid)

    if _user_has_samba_account(conn, uid):
        changes = {name: [(MODIFY_REPLACE, [value])] for name, value in samba_attrs.items()}
        conn.modify(user_dn, changes)
    else:
        changes = {
            'objectClass': [(MODIFY_ADD, ['sambaSamAccount', 'sambaIdmapEntry'])],
        }
        changes.update({name: [(MODIFY_ADD, [value])] for name, value in samba_attrs.items()})
        conn.modify(user_dn, changes)
    if conn.result['result'] != 0:
        raise NasLdapSyncError(f'Không cập nhật sambaSamAccount {uid}: {conn.result}')


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
    ldap_groups = _portal_ldap_group_names(user)
    if department_group in DEPARTMENT_LDAP_GROUPS:
        ldap_groups.add(department_group)
    primary_group = _primary_ldap_group_for_user(user, department_group)
    gid_number = _group_gid(conn, primary_group)

    user_dn = _user_dn(uid)
    created = not _user_exists(conn, uid)
    effective_password = (password or '').strip() or None
    if created and not effective_password:
        effective_password = _ldap_bind_password()

    if created:
        uid_number = _next_uid_number(conn)
        domain_sid = _read_domain_sid(conn)
        samba_rid = _next_samba_rid(conn)
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
            'userPassword': _ldap_password_hash(effective_password),
            **_samba_account_attrs(
                rid=samba_rid,
                password=effective_password,
                domain_sid=domain_sid,
            ),
        }
        conn.add(user_dn, USER_OBJECT_CLASSES, attrs)
        if conn.result['result'] != 0:
            raise NasLdapSyncError(f'Không tạo LDAP user {uid}: {conn.result}')
    else:
        uid_number = _user_uid_number(conn, uid)
        changes = {
            'cn': [(MODIFY_REPLACE, [display_name])],
            'sn': [(MODIFY_REPLACE, [sn])],
            'mail': [(MODIFY_REPLACE, [email])],
            'displayName': [(MODIFY_REPLACE, [display_name])],
            'gecos': [(MODIFY_REPLACE, [display_name])],
            'gidNumber': [(MODIFY_REPLACE, [gid_number])],
        }
        if effective_password:
            changes['userPassword'] = [(MODIFY_REPLACE, [_ldap_password_hash(effective_password)])]
        conn.modify(user_dn, changes)
        if conn.result['result'] != 0:
            raise NasLdapSyncError(f'Không cập nhật LDAP user {uid}: {conn.result}')
        if effective_password:
            _apply_samba_account(conn, uid=uid, password=effective_password)

    _sync_group_membership(conn, uid, ldap_groups)
    return {
        'status': 'ok',
        'uid': uid,
        'dn': user_dn,
        'created': created,
        'department_group': department_group,
        'ldap_groups': sorted(ldap_groups),
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
