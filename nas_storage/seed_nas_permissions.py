"""Seed nhóm + share + quyền mặc định cho module Phân quyền NAS."""

from __future__ import annotations

from django.db import transaction

from nas_storage.dept_nas_config import (
    DEPT_NAS_SPECS,
    EXTRA_SHARE_GROUP_LINKS,
    nas_principal_for_group,
)
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder
from nas_storage.permission_defs import default_read_write_flags


def seed_nas_permissions(*, dry_run: bool = False) -> dict:
    stats = {
        'groups_created': 0,
        'groups_updated': 0,
        'folders_created': 0,
        'folders_updated': 0,
        'permissions_created': 0,
        'permissions_updated': 0,
    }

    @transaction.atomic
    def _run():
        group_by_name: dict[str, NasAccessGroup] = {}

        for spec in DEPT_NAS_SPECS:
            principal = nas_principal_for_group(spec.nas_group)
            defaults = {
                'nas_principal': principal,
                'description': spec.label,
                'sort_order': spec.sort_order,
                'is_active': True,
                'portal_browse_all': spec.nas_group == 'TGD',
            }
            if dry_run:
                group_by_name[spec.nas_group] = NasAccessGroup(name=spec.nas_group, **defaults)
                continue

            group, created = NasAccessGroup.objects.update_or_create(
                name=spec.nas_group,
                defaults=defaults,
            )
            group_by_name[spec.nas_group] = group
            if created:
                stats['groups_created'] += 1
            else:
                stats['groups_updated'] += 1

            if not spec.share_name:
                continue

            folder_defaults = {
                'display_name': spec.label,
                'description': f'Share phòng ban · {spec.label}',
                'sort_order': spec.sort_order,
                'is_active': True,
            }
            folder, folder_created = NasShareFolder.objects.update_or_create(
                share_name=spec.share_name,
                parent=None,
                defaults=folder_defaults,
            )
            if folder_created:
                stats['folders_created'] += 1
            else:
                stats['folders_updated'] += 1

            perm_defaults = {
                'permission_type': 'allow',
                'apply_to': 'all',
                **default_read_write_flags(),
            }
            perm, perm_created = NasFolderPermission.objects.update_or_create(
                folder=folder,
                group=group,
                defaults=perm_defaults,
            )
            if perm_created:
                stats['permissions_created'] += 1
            else:
                stats['permissions_updated'] += 1

        for share_name, group_name in EXTRA_SHARE_GROUP_LINKS:
            group = group_by_name.get(group_name)
            if group is None and not dry_run:
                group = NasAccessGroup.objects.filter(name=group_name).first()
            if group is None:
                continue

            if dry_run:
                continue

            folder, folder_created = NasShareFolder.objects.get_or_create(
                share_name=share_name,
                parent=None,
                defaults={
                    'display_name': share_name,
                    'sort_order': group.sort_order,
                    'is_active': True,
                },
            )
            if folder_created:
                stats['folders_created'] += 1

            perm_defaults = {
                'permission_type': 'allow',
                'apply_to': 'all',
                **default_read_write_flags(),
            }
            _, perm_created = NasFolderPermission.objects.update_or_create(
                folder=folder,
                group=group,
                defaults=perm_defaults,
            )
            if perm_created:
                stats['permissions_created'] += 1

        if dry_run:
            transaction.set_rollback(True)

    _run()
    return stats
