"""Cấp quyền Xuất Excel + In cho mọi nhóm quyền (và fallback theo vai trò).

Chỉ bật cờ trên module/menu thực sự hỗ trợ endpoint tương ứng.

Usage:
    python manage.py grant_export_print
    python manage.py grant_export_print --dry-run
"""

from __future__ import annotations

from copy import deepcopy

from django.core.management.base import BaseCommand

from hrm.group_permissions import (
    PERM_EXPORT,
    PERM_PRINT,
    PERM_VIEW,
    empty_module_perm,
    menu_permission_action_enabled,
    module_supports_export,
    module_supports_print,
    normalize_module_entry,
)
from hrm.models import PermissionGroup, RoleModulePermission
from hrm.module_permissions import ALL_MODULE_KEYS
from hrm.submenu_registry import get_module_submenus, module_has_submenus


def _ensure_flags(entry: dict, *, module_key: str, menu_key: str | None = None) -> bool:
    """Bật export/print nếu module/menu hỗ trợ. Trả True nếu có thay đổi."""
    changed = False
    if menu_permission_action_enabled(module_key, menu_key, PERM_EXPORT):
        if not entry.get(PERM_EXPORT):
            entry[PERM_EXPORT] = True
            changed = True
    if menu_permission_action_enabled(module_key, menu_key, PERM_PRINT):
        if not entry.get(PERM_PRINT):
            entry[PERM_PRINT] = True
            changed = True
    # Có export/print thì luôn có view để nút/menu dùng được.
    if (entry.get(PERM_EXPORT) or entry.get(PERM_PRINT)) and not entry.get(PERM_VIEW):
        entry[PERM_VIEW] = True
        changed = True
    return changed


def grant_on_permissions(raw: dict | None) -> tuple[dict, int]:
    """Trả (perms_mới, số_cờ_đã_bật)."""
    source = deepcopy(raw) if isinstance(raw, dict) else {}
    flipped = 0

    for module_key in ALL_MODULE_KEYS:
        current = source.get(module_key)
        entry = normalize_module_entry(current, module_key=module_key)
        before = deepcopy(entry)

        if _ensure_flags(entry, module_key=module_key, menu_key=None):
            flipped += 1

        menus = entry.get('menus')
        if not isinstance(menus, dict):
            menus = {}

        menu_keys = {item['key'] for item in get_module_submenus(module_key)}
        menu_keys.update(menus.keys())

        if module_has_submenus(module_key):
            for menu_key in sorted(menu_keys):
                menu_entry = menus.get(menu_key)
                if not isinstance(menu_entry, dict):
                    # Chỉ tạo menu mới khi module đã có quyền xem / hoặc đang cấu hình menus
                    if menus or entry.get(PERM_VIEW):
                        menu_entry = empty_module_perm()
                        if entry.get(PERM_VIEW):
                            menu_entry[PERM_VIEW] = True
                    else:
                        continue
                else:
                    menu_entry = dict(menu_entry)
                if _ensure_flags(menu_entry, module_key=module_key, menu_key=menu_key):
                    flipped += 1
                menus[menu_key] = menu_entry
            entry['menus'] = menus
        elif menus:
            # Module không còn submenu registry nhưng JSON còn menus — vẫn cập nhật
            for menu_key, menu_entry in list(menus.items()):
                if not isinstance(menu_entry, dict):
                    continue
                menu_entry = dict(menu_entry)
                if _ensure_flags(menu_entry, module_key=module_key, menu_key=menu_key):
                    flipped += 1
                menus[menu_key] = menu_entry
            entry['menus'] = menus

        # Module không hỗ trợ export/print thì normalize sẽ tắt lại — không lưu rác
        if module_supports_export(module_key) or module_supports_print(module_key) or menus:
            if entry != before or module_key not in source:
                source[module_key] = entry
        elif module_key in source and entry != before:
            source[module_key] = entry

    return source, flipped


class Command(BaseCommand):
    help = 'Bật quyền Xuất Excel + In trên mọi nhóm quyền / fallback vai trò (khi module/menu hỗ trợ).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ báo số thay đổi, không ghi DB.',
        )

    def handle(self, *args, **options):
        dry = bool(options.get('dry_run'))
        groups_touched = 0
        roles_touched = 0
        flags = 0

        for group in PermissionGroup.objects.all().order_by('name'):
            new_perms, flipped = grant_on_permissions(group.module_permissions)
            if flipped:
                groups_touched += 1
                flags += flipped
                self.stdout.write(f'  nhóm {group.name}: +{flipped} cờ')
                if not dry:
                    group.module_permissions = new_perms
                    group.save(update_fields=['module_permissions'])

        for row in RoleModulePermission.objects.all().order_by('role'):
            new_perms, flipped = grant_on_permissions(row.module_permissions)
            if flipped:
                roles_touched += 1
                flags += flipped
                self.stdout.write(f'  vai trò {row.role}: +{flipped} cờ')
                if not dry:
                    row.module_permissions = new_perms
                    row.save(update_fields=['module_permissions'])

        mode = 'DRY-RUN' if dry else 'DONE'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: {groups_touched} nhóm quyền, {roles_touched} vai trò, {flags} cờ export/print.'
        ))
