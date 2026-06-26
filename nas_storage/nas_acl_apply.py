"""Áp dụng phân quyền Portal lên shared folder NAS (synoshare ACL)."""

from __future__ import annotations

import logging
import re
import shlex
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from nas_storage.dept_nas_config import is_portal_browse_hidden_share, portal_browse_hidden_shares
from nas_storage.models import NasFolderPermission
from nas_storage.permission_defs import PERM_TYPE_ALLOW, has_read_access, has_write_access

logger = logging.getLogger(__name__)


class NasAclApplyError(Exception):
    pass


def _ssh_host() -> str:
    explicit = (getattr(settings, 'NAS_SSH_HOST', '') or '').strip()
    if explicit:
        return explicit
    dsm = (getattr(settings, 'NAS_DSM_URL', '') or '').strip()
    host = urlparse(dsm).hostname
    if host:
        return host
    return ''


def _ssh_admin_credentials() -> tuple[str, str]:
    user = (getattr(settings, 'NAS_SSH_ADMIN_USER', '') or 'admin').strip()
    password = (getattr(settings, 'NAS_SSH_ADMIN_PASSWORD', '') or '').strip()
    if password:
        return user, password
    return user, (getattr(settings, 'NAS_DSM_PASSWORD', '') or '').strip()


def nas_acl_ssh_configured() -> bool:
    user, password = _ssh_admin_credentials()
    return bool(_ssh_host() and user and password)


def _synoshare_setuser_cmd(share: str, auth: str, operator: str, principals_csv: str) -> str:
    """principals_csv có thể chứa #everyone — bọc trong double quotes cho bash."""
    principals = (principals_csv or '').strip()
    if not principals:
        raise NasAclApplyError('Thiếu principal synoshare.')
    return f'/usr/syno/sbin/synoshare --setuser {share} {auth} {operator} "{principals}"'


def _run_ssh_commands(commands: list[str], *, timeout: int = 180) -> str:
    if not nas_acl_ssh_configured():
        raise NasAclApplyError('Chưa cấu hình NAS_SSH_HOST và mật khẩu admin SSH.')

    try:
        import paramiko
    except ImportError as exc:
        raise NasAclApplyError('Thiếu package paramiko trên server.') from exc

    host = _ssh_host()
    user, password = _ssh_admin_credentials()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, username=user, password=password, timeout=20)
        outputs: list[str] = []
        for cmd in commands:
            full = f"echo {shlex.quote(password)} | sudo -S bash -c {shlex.quote(cmd)} 2>&1"
            _, stdout, stderr = client.exec_command(full, timeout=timeout)
            out = (stdout.read() + stderr.read()).decode(errors='replace')
            outputs.append(out)
            if 'command not found' in out.lower() and 'synoshare' in cmd:
                raise NasAclApplyError('Không tìm thấy synoshare trên NAS.')
        return '\n'.join(outputs)
    except NasAclApplyError:
        raise
    except Exception as exc:
        logger.exception('NAS ACL SSH failed')
        raise NasAclApplyError(str(exc)) from exc
    finally:
        client.close()


def _share_access_level(perm: NasFolderPermission) -> str | None:
    if perm.permission_type != PERM_TYPE_ALLOW:
        return 'NA'
    flags = perm.permission_flags()
    if not has_read_access(flags):
        return 'NA'
    if has_write_access(flags):
        return 'RW'
    return 'RO'


def _normalize_principal(principal: str) -> str:
    p = (principal or '').strip()
    if not p:
        return ''
    return p if p.startswith('@') else f'@{p}'


_SHARE_ACL_LINE_RE = re.compile(
    r'ACL\s+(RW|RO|NA)\s+List\s+\.+?\[(.*)\]',
    re.IGNORECASE,
)

PRESERVED_SHARE_PRINCIPAL_KEYS = frozenset({
    'administrators',
    'admin',
    'guest',
    'users',
    'everyone',
    'containermanager',
    'tailscale-justplay',
    'justplay-it',
})


def principal_group_key(principal: str) -> str:
    p = (principal or '').strip().lstrip('@')
    if '@' in p:
        return p.split('@', 1)[0].lower()
    return p.lower()


def parse_synoshare_list_acl(output: str) -> dict[str, set[str]]:
    buckets: dict[str, set[str]] = {'RW': set(), 'RO': set(), 'NA': set()}
    for line in (output or '').splitlines():
        match = _SHARE_ACL_LINE_RE.search(line)
        if not match:
            continue
        level = match.group(1).upper()
        raw = (match.group(2) or '').strip()
        if not raw:
            continue
        for item in raw.split(','):
            principal = item.strip()
            if principal:
                buckets[level].add(principal)
    return buckets


def portal_managed_group_keys() -> set[str]:
    from nas_storage.dept_nas_config import DEPARTMENT_NAS_GROUPS
    from nas_storage.models import NasAccessGroup

    keys = {name.lower() for name in DEPARTMENT_NAS_GROUPS}
    for name in NasAccessGroup.objects.filter(is_active=True).values_list('name', flat=True):
        keys.add((name or '').strip().lower())
    return keys


def portal_managed_user_keys() -> set[str]:
    from nas_storage.models import NasFolderPermission

    keys: set[str] = set()
    for username in NasFolderPermission.objects.filter(user__isnull=False).values_list(
        'user__username',
        flat=True,
    ):
        if username:
            keys.add(username.lower())
    return keys


def portal_managed_share_keys() -> set[str]:
    return portal_managed_group_keys() | portal_managed_user_keys()


def is_portal_managed_share_principal(principal: str) -> bool:
    if (principal or '').strip() == '#everyone':
        return False
    key = principal_group_key(principal)
    if not key or key in PRESERVED_SHARE_PRINCIPAL_KEYS:
        return False
    return key in portal_managed_share_keys()


def _active_folder_permissions(folder):
    from django.db.models import Q

    from nas_storage.models import NasFolderPermission

    return (
        NasFolderPermission.objects.filter(folder=folder)
        .select_related('group', 'user')
        .filter(
            Q(group__isnull=False, group__is_active=True)
            | Q(user__isnull=False, user__is_active=True),
        )
        .order_by('id')
    )


def _desired_share_acl_buckets(folder) -> dict[str, set[str]]:
    buckets: dict[str, set[str]] = {'RW': set(), 'RO': set(), 'NA': set()}
    for perm in _active_folder_permissions(folder):
        level = _share_access_level(perm)
        if not level:
            continue
        principal = perm.resolved_nas_principal()
        if principal:
            buckets[level].add(principal)
    return buckets


def build_share_acl_sync_commands(
    *,
    share: str,
    desired: dict[str, set[str]],
    current: dict[str, set[str]],
) -> list[str]:
    """Sinh lệnh synoshare: gỡ principal Portal không còn cấu hình, thêm/cập nhật còn lại."""
    commands: list[str] = []
    managed_keys = portal_managed_share_keys()

    for principal_key in sorted(managed_keys):
        desired_level: str | None = None
        desired_principal: str | None = None
        for level in ('RW', 'RO', 'NA'):
            for principal in desired.get(level, set()):
                if principal_group_key(principal) == principal_key:
                    desired_level = level
                    desired_principal = principal
                    break
            if desired_level:
                break

        for level in ('RW', 'RO', 'NA'):
            existing = _find_principal_in_bucket(current.get(level, set()), principal_key)
            if existing and (desired_level is None or level != desired_level):
                commands.append(_synoshare_setuser_cmd(share, level, '-', existing))

        if desired_level and desired_principal:
            existing_desired = _find_principal_in_bucket(
                current.get(desired_level, set()),
                principal_key,
            )
            if not existing_desired:
                commands.append(
                    f'/usr/syno/sbin/synoshare --setuser {share} {desired_level} + {desired_principal}'
                )

    return commands


def _find_principal_in_bucket(bucket: set[str], principal_key: str) -> str | None:
    for principal in bucket:
        if principal_group_key(principal) == principal_key:
            return principal
    return None


def apply_folder_permissions(folder) -> dict:
    """Đồng bộ ACL share NAS theo cấu hình Portal cho một folder."""
    share = folder.share_name
    perms = list(_active_folder_permissions(folder))
    desired = _desired_share_acl_buckets(folder)

    list_output = _run_ssh_commands([f'/usr/syno/sbin/synoshare --list_acl {share}'])
    current = parse_synoshare_list_acl(list_output)
    sync_commands = build_share_acl_sync_commands(
        share=share,
        desired=desired,
        current=current,
    )

    commands = [f'/usr/syno/sbin/synoshare --list_acl {share}', *sync_commands]
    if sync_commands:
        commands.append(f'/usr/syno/sbin/synoshare --list_acl {share}')
    output = _run_ssh_commands(commands) if sync_commands else list_output

    now = timezone.now()
    for perm in perms:
        perm.last_applied_at = now
        perm.last_apply_status = 'ok'
        perm.save(update_fields=['last_applied_at', 'last_apply_status', 'updated_at'])

    if not perms and not sync_commands:
        return {'status': 'skipped', 'reason': 'no_changes'}

    return {
        'status': 'ok',
        'share': share,
        'removed': sum(1 for cmd in sync_commands if ' - ' in cmd),
        'added': sum(1 for cmd in sync_commands if ' + ' in cmd),
        'output': output[-2000:],
    }


def _synoacl_mask(access_level: str) -> str:
    if access_level == 'RO':
        return 'r-x---a-R-c--:fd--'
    return 'rwxpdDaARWc--:fd--'


def revoke_user_folder_acl(grant) -> dict:
    """Gỡ ACL thư mục con của user trên NAS (khi xóa / tắt truy cập riêng)."""
    target = grant.volume_target_path()
    principal = grant.resolved_user_principal()
    ace_prefix = f'user:{principal}:allow'
    commands = [
        f'/usr/syno/bin/synoacltool -get "{target}"',
        f'/usr/syno/bin/synoacltool -del "{target}" {ace_prefix}',
        f'/usr/syno/bin/synoacltool -get "{target}"',
    ]
    output = _run_ssh_commands(commands)
    now = timezone.now()
    grant.last_applied_at = now
    grant.last_apply_status = 'revoked'
    grant.save(update_fields=['last_applied_at', 'last_apply_status', 'updated_at'])
    return {
        'status': 'ok',
        'path': target,
        'principal': principal,
        'output': output[-2000:],
    }


def apply_user_folder_acl(grant) -> dict:
    """Áp dụng ACL thư mục con cho một user (RaiDrive / SMB / synoacltool)."""
    if not grant.is_active:
        return {'status': 'skipped', 'reason': 'inactive'}

    target = grant.volume_target_path()
    principal = grant.resolved_user_principal()
    mask = _synoacl_mask(grant.access_level)
    ace = f'user:{principal}:allow:{mask}'

    commands = [
        f'/usr/syno/bin/synoacltool -get "{target}"',
        f'/usr/syno/bin/synoacltool -add "{target}" {ace}',
        f'/usr/syno/bin/synoacltool -get "{target}"',
    ]
    output = _run_ssh_commands(commands)
    now = timezone.now()
    grant.last_applied_at = now
    grant.last_apply_status = 'ok'
    grant.save(update_fields=['last_applied_at', 'last_apply_status', 'updated_at'])

    return {
        'status': 'ok',
        'path': target,
        'principal': principal,
        'output': output[-2000:],
    }


def apply_all_user_folder_acls() -> dict:
    from nas_storage.models import NasUserFolderAcl

    stats = {'ok': 0, 'skipped': 0, 'errors': []}
    for grant in NasUserFolderAcl.objects.filter(is_active=True).select_related('user', 'folder'):
        try:
            result = apply_user_folder_acl(grant)
            if result.get('status') == 'ok':
                stats['ok'] += 1
            else:
                stats['skipped'] += 1
        except NasAclApplyError as exc:
            stats['errors'].append(f'{grant}: {exc}')
    return stats


def apply_all_folder_permissions() -> dict:
    from nas_storage.models import NasShareFolder

    stats = {'ok': 0, 'skipped': 0, 'errors': []}
    for folder in NasShareFolder.objects.filter(is_active=True).order_by('sort_order', 'share_name'):
        try:
            result = apply_folder_permissions(folder)
            if result.get('status') == 'ok':
                stats['ok'] += 1
            else:
                stats['skipped'] += 1
        except NasAclApplyError as exc:
            stats['errors'].append(f'{folder.share_name}: {exc}')
    return stats


def discover_shares_from_nas() -> list[dict]:
    """Liệt kê share từ NAS (synoshare --enum ALL)."""
    if not nas_acl_ssh_configured():
        raise NasAclApplyError('Chưa cấu hình SSH NAS.')
    output = _run_ssh_commands(['/usr/syno/sbin/synoshare --enum ALL'])
    names = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith('Password') or 'Listed' in line:
            continue
        if re.match(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*$', line):
            names.append(line)
    return [
        {'share_name': n, 'display_name': n}
        for n in names
        if not is_portal_browse_hidden_share(n)
    ]


def lock_hidden_share_acl(share_name: str) -> dict:
    """
    Khóa share hệ thống trên DSM (vd. docker): bỏ #everyone, chặn nhóm LDAP, ẩn browse.
    Giữ quyền RW hiện có cho IT/admin (không ghi đè RW list).
    """
    from nas_storage.dept_nas_config import DEPARTMENT_NAS_GROUPS

    share = (share_name or '').strip()
    if not share:
        raise NasAclApplyError('Thiếu tên share.')
    na_principals = ','.join(f'@{g}' for g in sorted(DEPARTMENT_NAS_GROUPS) if g != 'IT')
    extra_na = '@users,guest'
    rw_keep = '@IT,admin,tailscale-justplay,justplay-it,ContainerManager,@administrators'
    commands = [
        f'/usr/syno/sbin/synoshare --list_acl {share}',
        f'/usr/syno/sbin/synoshare --set_share_default_acl {share}',
        _synoshare_setuser_cmd(share, 'RW', '+', rw_keep),
        _synoshare_setuser_cmd(share, 'NA', '+', f'{na_principals},{extra_na}'),
        f'/usr/syno/sbin/synoshare --setbrowse {share} 0',
        f'/usr/syno/sbin/synoshare --list_acl {share}',
    ]
    output = _run_ssh_commands(commands)
    return {'status': 'ok', 'share': share, 'output': output[-2000:]}


def lock_all_hidden_shares_acl() -> list[dict]:
    results = []
    for share in sorted(portal_browse_hidden_shares()):
        try:
            results.append(lock_hidden_share_acl(share))
        except NasAclApplyError as exc:
            results.append({'status': 'error', 'share': share, 'error': str(exc)})
    return results
