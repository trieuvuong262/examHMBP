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


def _run_ssh_commands(commands: list[str], *, timeout: int = 180, client=None) -> str:
    if not nas_acl_ssh_configured():
        raise NasAclApplyError('Chưa cấu hình NAS_SSH_HOST và mật khẩu admin SSH.')

    try:
        import paramiko
    except ImportError as exc:
        raise NasAclApplyError('Thiếu package paramiko trên server.') from exc

    host = _ssh_host()
    user, password = _ssh_admin_credentials()
    own_client = client is None
    if own_client:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if own_client:
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
        if own_client:
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


def _nas_ldap_domain() -> str:
    return (getattr(settings, 'NAS_LDAP_DOMAIN', 'ldap.justplay.local') or 'ldap.justplay.local').strip().lower()


def is_fq_ldap_principal(principal: str) -> bool:
    """Principal đầy đủ domain LDAP (@IT@ldap... hoặc user@ldap...)."""
    p = (principal or '').strip()
    if not p:
        return False
    domain = _nas_ldap_domain()
    lower = p.lower()
    return lower.endswith(f'@{domain}') or lower.endswith(domain)


def principal_should_upgrade(existing: str, desired: str) -> bool:
    """
    NAS còn principal rút gọn (@IT, @HCNS) trong khi Portal dùng @IT@ldap.justplay.local.
    WebDAV map theo nhóm LDAP đầy đủ — không coi @IT và @IT@ldap... là tương đương.
    """
    if not existing or not desired or existing == desired:
        return False
    if principal_group_key(existing) != principal_group_key(desired):
        return False
    return is_fq_ldap_principal(desired) and not is_fq_ldap_principal(existing)


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


def _user_nas_principal(user) -> str:
    domain = _nas_ldap_domain()
    return f'{user.username}@{domain}'


def _portal_synced_user_principals() -> set[str]:
    """Principal user cần trên share ACL theo thành viên nhóm Portal (NasFolderPermission.group)."""
    from nas_storage.models import NasFolderPermission
    from nas_storage.portal_access import portal_users_for_access_group

    principals: set[str] = set()
    qs = NasFolderPermission.objects.filter(
        group__isnull=False,
        group__is_active=True,
    ).select_related('group')
    for perm in qs:
        if not _share_access_level(perm):
            continue
        for user in portal_users_for_access_group(perm.group):
            principals.add(_user_nas_principal(user))
    return principals


def portal_managed_user_keys() -> set[str]:
    from nas_storage.models import NasFolderPermission

    keys: set[str] = set()
    for username in NasFolderPermission.objects.filter(user__isnull=False).values_list(
        'user__username',
        flat=True,
    ):
        if username:
            keys.add(username.lower())
    for principal in _portal_synced_user_principals():
        keys.add(principal_group_key(principal))
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
    from nas_storage.portal_access import portal_users_for_access_group

    buckets: dict[str, set[str]] = {'RW': set(), 'RO': set(), 'NA': set()}
    for perm in _active_folder_permissions(folder):
        level = _share_access_level(perm)
        if not level:
            continue
        principal = perm.resolved_nas_principal()
        if principal:
            buckets[level].add(principal)
        if perm.group_id:
            for user in portal_users_for_access_group(perm.group):
                buckets[level].add(_user_nas_principal(user))
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
            if existing_desired and principal_should_upgrade(existing_desired, desired_principal):
                commands.append(_synoshare_setuser_cmd(share, desired_level, '-', existing_desired))
                commands.append(
                    f'/usr/syno/sbin/synoshare --setuser {share} {desired_level} + {desired_principal}'
                )
            elif not existing_desired:
                commands.append(
                    f'/usr/syno/sbin/synoshare --setuser {share} {desired_level} + {desired_principal}'
                )

    return commands


def _find_principal_in_bucket(bucket: set[str], principal_key: str) -> str | None:
    for principal in bucket:
        if principal_group_key(principal) == principal_key:
            return principal
    return None


def directory_exists_on_nas(path: str, *, share_name: str = '', client=None) -> bool:
    """Kiểm tra thư mục đã tồn tại trên NAS (không tạo mới)."""
    from nas_storage.nas_paths import NasPathError, normalize_volume_path

    try:
        target = normalize_volume_path(path, share_name=share_name)
    except NasPathError:
        return False
    if not target.startswith('/volume'):
        return False
    if not nas_acl_ssh_configured():
        return False
    try:
        out = _run_ssh_commands([
            f'test -d {shlex.quote(target)} && echo YES || echo NO',
        ], client=client)
        return 'YES' in (out or '')
    except NasAclApplyError:
        return False


def ensure_directory_on_nas(path: str, *, share_name: str = '', client=None) -> str:
    """Tạo thư mục trên NAS (mkdir -p) nếu chưa có."""
    from nas_storage.nas_paths import NasPathError, normalize_volume_path

    try:
        target = normalize_volume_path(path, share_name=share_name)
    except NasPathError as exc:
        raise NasAclApplyError(str(exc)) from exc
    if not target.startswith('/volume'):
        raise NasAclApplyError(f'Đường dẫn NAS không hợp lệ: {target}')
    return _run_ssh_commands([
        f'mkdir -p {shlex.quote(target)}',
        f'test -d {shlex.quote(target)} && echo OK',
    ], client=client)


def _parse_synoshare_enum(output: str) -> list[str]:
    names = []
    for line in (output or '').splitlines():
        line = line.strip()
        if not line or line.startswith('Password') or 'Listed' in line:
            continue
        if re.match(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*$', line):
            names.append(line)
    return names


def list_shares_on_nas() -> list[str]:
    if not nas_acl_ssh_configured():
        return []
    output = _run_ssh_commands(['/usr/syno/sbin/synoshare --enum ALL'])
    return _parse_synoshare_enum(output)


def share_exists_on_nas(share_name: str) -> bool:
    key = (share_name or '').strip().lower()
    if not key:
        return False
    return key in {n.lower() for n in list_shares_on_nas()}


def create_share_on_nas(folder) -> dict:
    """Tạo shared folder mới trên DSM (synoshare --add)."""
    from nas_storage.nas_paths import normalize_volume_path

    share = (folder.share_name or '').strip()
    if not share:
        raise NasAclApplyError('Thiếu tên share.')
    path = normalize_volume_path(folder.volume_path, share_name=share)
    desc = (folder.display_name or share).replace('"', '\\"')[:64]
    cmd = (
        f'/usr/syno/sbin/synoshare --add {share} "{desc}" '
        f'{shlex.quote(path)} "" "" "" 1 0'
    )
    output = _run_ssh_commands([cmd])
    lower = output.lower()
    if 'error' in lower and 'exist' not in lower and 'already' not in lower:
        raise NasAclApplyError(output[-800:])
    if not share_exists_on_nas(share):
        raise NasAclApplyError(
            f'synoshare không tạo được share «{share}». Kiểm tra đường dẫn {path}. '
            f'Output: {output[-400:]}'
        )
    return {'status': 'ok', 'action': 'share_add', 'share': share, 'path': path}


def provision_portal_folder_on_nas(folder) -> dict:
    """
    [Đã tắt trên Portal] Tạo thư mục/share qua SSH — chỉ dùng trong test/management command.
    UI «Tạo trên NAS» đã gỡ; thư mục phải tạo thủ công trên Synology.
    """
    if not nas_acl_ssh_configured():
        raise NasAclApplyError('Chưa cấu hình SSH NAS.')
    if folder.parent_id:
        target = folder.resolved_volume_path()
        output = ensure_directory_on_nas(target)
        return {'status': 'ok', 'action': 'mkdir', 'path': target, 'output': output[-500:]}
    share = (folder.share_name or '').strip()
    if share_exists_on_nas(share):
        ensure_directory_on_nas(folder.resolved_volume_path())
        return {'status': 'skipped', 'reason': 'share_exists', 'share': share}
    return create_share_on_nas(folder)


def _synoacl_ace_for_permission(perm: NasFolderPermission) -> str | None:
    level = _share_access_level(perm)
    if not level or level == 'NA':
        return None
    mask = _synoacl_mask('RO' if level == 'RO' else 'RW')
    principal = perm.resolved_nas_principal()
    if perm.user_id:
        return f'user:{principal}:allow:{mask}'
    if perm.group_id:
        return f'group:{principal.lstrip("@")}:allow:{mask}'
    return None


def apply_subfolder_permissions(folder, *, client=None) -> dict:
    """Đồng bộ ACL thư mục con (synoacltool) theo quyền hiệu lực (kế thừa + local)."""
    from nas_storage.folder_permissions_resolved import effective_folder_permissions

    target = folder.resolved_volume_path()
    effective = effective_folder_permissions(folder)
    local_perms = list(_active_folder_permissions(folder))

    if not directory_exists_on_nas(target, share_name=folder.share_name, client=client):
        return {'status': 'skipped', 'reason': 'path_missing_on_nas', 'path': target}

    commands = [f'/usr/syno/bin/synoacltool -get "{target}"']
    applied = 0
    for item in effective:
        ace = _synoacl_ace_for_permission(item.permission)
        if not ace:
            continue
        commands.append(f'/usr/syno/bin/synoacltool -add "{target}" {ace}')
        applied += 1
    commands.append(f'/usr/syno/bin/synoacltool -get "{target}"')

    output = _run_ssh_commands(commands, client=client) if applied else ''
    now = timezone.now()
    for perm in local_perms:
        perm.last_applied_at = now
        perm.last_apply_status = 'ok'
        perm.save(update_fields=['last_applied_at', 'last_apply_status', 'updated_at'])

    if not applied:
        return {'status': 'skipped', 'reason': 'no_effective_permissions'}

    return {
        'status': 'ok',
        'path': target,
        'applied': applied,
        'output': output[-2000:] if output else '',
    }


def apply_folder_permissions(folder, *, client=None) -> dict:
    """Đồng bộ ACL NAS theo cấu hình Portal cho một thư mục (share gốc hoặc thư mục con)."""
    if folder.parent_id:
        grant = private_user_folder_acl_grant_for_folder(folder)
        if grant:
            top = (grant.sub_path or '').strip().strip('/')
            folder_seg = (folder.sub_path or '').strip().strip('/')
            if folder_seg.lower() == top.lower():
                return apply_user_folder_acl(grant, client=client)
            return {'status': 'skipped', 'reason': 'under_private_user_folder'}
        return apply_subfolder_permissions(folder, client=client)

    share = folder.share_name
    perms = list(_active_folder_permissions(folder))
    desired = _desired_share_acl_buckets(folder)

    list_output = _run_ssh_commands([f'/usr/syno/sbin/synoshare --list_acl {share}'], client=client)
    current = parse_synoshare_list_acl(list_output)
    sync_commands = build_share_acl_sync_commands(
        share=share,
        desired=desired,
        current=current,
    )

    commands = [f'/usr/syno/sbin/synoshare --list_acl {share}', *sync_commands]
    if sync_commands:
        commands.append(f'/usr/syno/sbin/synoshare --list_acl {share}')
    output = _run_ssh_commands(commands, client=client) if sync_commands else list_output

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


_SYNOACL_INDEX_LINE = re.compile(r'^\s*\[(\d+)\].*\(level:(\d+)\)\s*$')
_SYNOACLTOL = '/usr/syno/bin/synoacltool'
_PRIVATE_FOLDER_ADMIN_ACE = 'group:administrators:allow:rwxpdDaARWc--:fd--'


def _synoacl_indices_at_level(get_output: str, *, level: int = 0) -> list[int]:
    """Chỉ số ACE local (level 0) — xóa ngược để synoacltool -del không lệch index."""
    indices: list[int] = []
    for line in (get_output or '').splitlines():
        m = _SYNOACL_INDEX_LINE.match(line.strip())
        if not m:
            continue
        if int(m.group(2)) == level:
            indices.append(int(m.group(1)))
    return sorted(indices, reverse=True)


def private_user_folder_acl_grant_for_folder(folder):
    """
    Grant NasUserFolderAcl nếu thư mục Portal là hoặc nằm dưới thư mục riêng user
    (vd. 05_MARKETING/lvanhthu hoặc 05_MARKETING/lvanhthu/Download).
    """
    from nas_storage.models import NasShareFolder, NasUserFolderAcl

    if not folder or not isinstance(folder, NasShareFolder):
        return None

    parts: list[str] = []
    current = folder
    while current:
        seg = (current.sub_path or '').strip().strip('/')
        if seg:
            parts.insert(0, seg)
        current = current.parent
    if not parts:
        return None

    share_root = folder
    while share_root.parent_id:
        share_root = share_root.parent

    top_seg = parts[0]
    return (
        NasUserFolderAcl.objects.filter(
            folder_id=share_root.pk,
            is_active=True,
            sub_path__iexact=top_seg,
        )
        .select_related('user', 'folder')
        .first()
    )


def is_private_user_folder_portal_record(folder) -> bool:
    return private_user_folder_acl_grant_for_folder(folder) is not None


def _portal_group_principals_for_share(share_name: str) -> list[str]:
    """Principal nhóm Portal trên share gốc — gỡ khỏi thư mục riêng user."""
    from nas_storage.models import NasShareFolder

    folder = (
        NasShareFolder.objects.filter(share_name=share_name, parent__isnull=True, is_active=True)
        .first()
    )
    if not folder:
        return []
    principals: list[str] = []
    seen: set[str] = set()
    for perm in _active_folder_permissions(folder):
        if not perm.group_id:
            continue
        principal = (perm.resolved_nas_principal() or '').strip().lstrip('@')
        if not principal or principal in seen:
            continue
        seen.add(principal)
        principals.append(principal)
    return principals


def apply_user_folder_acl(grant, *, client=None) -> dict:
    """Áp dụng ACL thư mục riêng — chỉ owner + administrators, không kế thừa MKT/TGD."""
    if not grant.is_active:
        return {'status': 'skipped', 'reason': 'inactive'}

    target = grant.volume_target_path()
    principal = grant.resolved_user_principal()
    mask = _synoacl_mask(grant.access_level)
    owner_ace = f'user:{principal}:allow:{mask}'

    get_output = _run_ssh_commands([f'{_SYNOACLTOL} -get "{target}"'], client=client)
    commands: list[str] = [
        f'{_SYNOACLTOL} -del-archive "{target}" is_inherit',
    ]
    for idx in _synoacl_indices_at_level(get_output, level=0):
        commands.append(f'{_SYNOACLTOL} -del "{target}" {idx}')
    commands.extend([
        f'{_SYNOACLTOL} -add "{target}" {owner_ace}',
        f'{_SYNOACLTOL} -add "{target}" {_PRIVATE_FOLDER_ADMIN_ACE}',
        f'{_SYNOACLTOL} -get "{target}"',
    ])
    output = _run_ssh_commands(commands, client=client)
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
    folders = list(
        NasShareFolder.objects.filter(is_active=True)
        .order_by('parent_id', 'sort_order', 'share_name', 'sub_path')
    )
    if not folders:
        return stats
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
        for folder in folders:
            label = folder.portal_path_label()
            try:
                result = apply_folder_permissions(folder, client=client)
                if result.get('status') == 'ok':
                    stats['ok'] += 1
                else:
                    stats['skipped'] += 1
            except NasAclApplyError as exc:
                stats['errors'].append(f'{label}: {exc}')
            except Exception as exc:
                logger.exception('apply_folder_permissions failed for %s', label)
                stats['errors'].append(f'{label}: {exc}')
    except NasAclApplyError:
        raise
    except Exception as exc:
        logger.exception('NAS ACL batch SSH failed')
        raise NasAclApplyError(str(exc)) from exc
    finally:
        client.close()
    return stats


def discover_shares_from_nas() -> list[dict]:
    """Liệt kê share từ NAS (synoshare --enum ALL)."""
    if not nas_acl_ssh_configured():
        raise NasAclApplyError('Chưa cấu hình SSH NAS.')
    output = _run_ssh_commands(['/usr/syno/sbin/synoshare --enum ALL'])
    names = _parse_synoshare_enum(output)
    return [
        {'share_name': n, 'display_name': n}
        for n in names
        if not is_portal_browse_hidden_share(n)
    ]


def _should_skip_import_dir_segment(name: str) -> bool:
    n = (name or '').strip()
    if not n or n.startswith('.'):
        return True
    if n.startswith('@') or n in {'#recycle', '#snapshot'}:
        return True
    return is_portal_browse_hidden_share(n)


def _insert_path_into_import_tree(tree: dict[str, dict], parts: list[str]) -> None:
    if not parts:
        return
    seg = parts[0]
    if seg not in tree:
        tree[seg] = {'sub_path': seg, 'display_name': seg, '_kids': {}}
    if len(parts) > 1:
        _insert_path_into_import_tree(tree[seg]['_kids'], parts[1:])


def _import_tree_dict_to_list(tree: dict[str, dict]) -> list[dict]:
    result: list[dict] = []
    for seg in sorted(tree.keys()):
        node = tree[seg]
        result.append({
            'sub_path': node['sub_path'],
            'display_name': node['display_name'],
            'children': _import_tree_dict_to_list(node['_kids']),
        })
    return result


def _parse_find_dirs_to_tree(base_path: str, output: str, *, max_depth: int) -> list[dict]:
    base = base_path.rstrip('/')
    tree: dict[str, dict] = {}
    for line in (output or '').splitlines():
        path = line.strip()
        if not path or not path.startswith(base):
            continue
        rel = path[len(base):].strip('/')
        if not rel:
            continue
        parts = [p for p in rel.split('/') if p]
        if not parts or len(parts) > max_depth:
            continue
        if any(_should_skip_import_dir_segment(p) for p in parts):
            continue
        _insert_path_into_import_tree(tree, parts)
    return _import_tree_dict_to_list(tree)


def discover_share_tree_from_nas(*, max_child_depth: int = 2) -> list[dict]:
    """Liệt kê share gốc + thư mục con trên NAS (tối đa max_child_depth cấp dưới share)."""
    roots = discover_shares_from_nas()
    if max_child_depth <= 0:
        return [{**item, 'children': []} for item in roots]

    result: list[dict] = []
    for item in roots:
        share_name = item['share_name']
        base = f'/volume1/{share_name}'
        children: list[dict] = []
        try:
            cmd = (
                f'find {shlex.quote(base)} -mindepth 1 -maxdepth {max_child_depth} '
                f'-type d 2>/dev/null'
            )
            output = _run_ssh_commands([cmd])
            children = _parse_find_dirs_to_tree(base, output, max_depth=max_child_depth)
        except NasAclApplyError:
            children = []
        result.append({
            'share_name': share_name,
            'display_name': item['display_name'],
            'children': children,
        })
    return result


def _count_tree_children(nodes: list[dict]) -> int:
    total = 0
    for node in nodes:
        total += 1
        total += _count_tree_children(node.get('children') or [])
    return total


def import_folder_tree_from_nas(trees: list[dict]) -> dict:
    """Đăng ký share gốc + cây thư mục con lên Portal (không xóa / không tạo trên NAS)."""
    from nas_storage.models import NasShareFolder

    stats = {'roots_created': 0, 'children_created': 0, 'roots_updated': 0}

    def walk_children(parent: NasShareFolder, children: list[dict]) -> None:
        for child in children:
            folder, created = NasShareFolder.objects.get_or_create(
                parent=parent,
                sub_path=child['sub_path'],
                defaults={
                    'display_name': child.get('display_name') or child['sub_path'],
                    'inherits_permissions': True,
                },
            )
            if created:
                stats['children_created'] += 1
            walk_children(folder, child.get('children') or [])

    for tree in trees:
        root, created = NasShareFolder.objects.get_or_create(
            share_name=tree['share_name'],
            parent=None,
            defaults={'display_name': tree.get('display_name') or tree['share_name']},
        )
        if created:
            stats['roots_created'] += 1
        elif not (root.display_name or '').strip():
            root.display_name = tree.get('display_name') or tree['share_name']
            root.save(update_fields=['display_name', 'updated_at'])
            stats['roots_updated'] += 1
        walk_children(root, tree.get('children') or [])

    return stats


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
