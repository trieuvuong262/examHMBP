"""Gán user local DSM vào nhóm phòng ban trên NAS (synogroup)."""

from __future__ import annotations

import re

from django.contrib.auth.models import User

from hrm.models import Profile
from nas_storage.dept_nas_config import (
    NAS_LOCAL_SYNC_SKIP_USERS,
    nas_group_for_portal_department,
    nas_group_for_user_description,
)
from nas_storage.nas_acl_apply import NasAclApplyError, _run_ssh_commands

_RE_LOCAL_USER = re.compile(r'^[A-Za-z0-9_.-]+$')


def _parse_synouser_enum(output: str) -> list[str]:
    users: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith('Password') or 'Listed' in line:
            continue
        if _RE_LOCAL_USER.match(line):
            users.append(line)
    return users


def _parse_synouser_get(output: str, field: str) -> str:
    prefix = f'{field}:'
    for line in output.splitlines():
        if line.strip().lower().startswith(prefix.lower()):
            return line.split(':', 1)[1].strip()
    return ''


def list_local_nas_users() -> list[dict]:
    """Liệt kê user local trên NAS kèm mô tả (Description)."""
    raw = _run_ssh_commands(['/usr/syno/sbin/synouser --enum ALL'])
    users = _parse_synouser_enum(raw)
    rows: list[dict] = []
    for username in users:
        if username.lower() in NAS_LOCAL_SYNC_SKIP_USERS:
            continue
        detail = _run_ssh_commands([f'/usr/syno/sbin/synouser --get {username}'])
        description = _parse_synouser_get(detail, 'Description')
        rows.append({'username': username, 'description': description})
    return rows


def _portal_user_group_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    qs = (
        Profile.objects.filter(is_employed=True, user__is_active=True)
        .select_related('user', 'department')
        .values_list('user__username', 'department__name')
    )
    for username, dept_name in qs:
        login = (username or '').strip()
        if not login or login.lower() in NAS_LOCAL_SYNC_SKIP_USERS:
            continue
        group = nas_group_for_portal_department(dept_name)
        if group:
            mapping[login] = group
    return mapping


def build_local_group_assignments(*, include_dsm_description: bool = True) -> dict[str, str]:
    """
    username → NAS group.
    Ưu tiên phòng ban Portal; fallback mô tả DSM cho user chỉ có trên NAS.
    """
    assignments = dict(_portal_user_group_map())
    if not include_dsm_description:
        return assignments

    for row in list_local_nas_users():
        username = row['username']
        if username in assignments:
            continue
        group = nas_group_for_user_description(row.get('description'))
        if group:
            assignments[username] = group
    return assignments


def sync_nas_local_group_members(
    *,
    dry_run: bool = False,
    include_dsm_description: bool = True,
) -> dict:
    if not dry_run:
        try:
            from nas_storage.nas_acl_apply import nas_acl_ssh_configured

            if not nas_acl_ssh_configured():
                raise NasAclApplyError('Chưa cấu hình NAS_SSH_HOST / NAS_SSH_ADMIN_PASSWORD.')
        except NasAclApplyError:
            raise

    assignments = build_local_group_assignments(include_dsm_description=include_dsm_description)
    stats = {'assigned': 0, 'skipped': 0, 'errors': [], 'planned': []}

    for username, group in sorted(assignments.items()):
        stats['planned'].append(f'{username} → {group}')
        if dry_run:
            continue
        try:
            out = _run_ssh_commands([
                f'/usr/syno/sbin/synogroup --memberadd {group} {username}',
            ])
            if 'not found' in out.lower() or 'error' in out.lower():
                if 'already' not in out.lower() and 'exist' not in out.lower():
                    stats['errors'].append(f'{username}: {out.strip()[:200]}')
                    continue
            stats['assigned'] += 1
        except NasAclApplyError as exc:
            stats['errors'].append(f'{username}: {exc}')

    stats['skipped'] = len(assignments) - stats['assigned'] if not dry_run else 0
    return stats


def sync_portal_users_preview() -> list[dict]:
    """Xem trước map Portal → nhóm NAS (không SSH)."""
    rows: list[dict] = []
    profiles = (
        Profile.objects.filter(is_employed=True, user__is_active=True)
        .select_related('user', 'department')
        .order_by('user__username')
    )
    for profile in profiles:
        user: User = profile.user
        group = nas_group_for_portal_department(profile.department.name if profile.department else '')
        rows.append({
            'username': user.username,
            'department': profile.department.name if profile.department else '',
            'nas_group': group or '—',
        })
    return rows
