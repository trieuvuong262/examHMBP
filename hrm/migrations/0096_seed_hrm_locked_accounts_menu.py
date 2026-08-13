"""Seed menu con Nhân sự: Danh sách nhân viên + Tài khoản bị khóa."""

from django.db import migrations

NEW_MENU_KEYS = ('users', 'locked_accounts')


def _flags(source) -> dict:
    if not isinstance(source, dict):
        source = {}
    return {
        'view': bool(source.get('view')),
        'create': bool(source.get('create')),
        'update': bool(source.get('update')),
        'delete': bool(source.get('delete')),
        'export': bool(source.get('export')),
        'print': bool(source.get('print')),
    }


def _has_any(flags: dict) -> bool:
    return any(flags.get(key) for key in ('view', 'create', 'update', 'delete', 'export', 'print'))


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        hrm = dict(perms.get('hrm') or {})
        if not hrm:
            continue
        menus = dict(hrm.get('menus') or {}) if isinstance(hrm.get('menus'), dict) else {}
        module_flags = _flags(hrm)
        if not _has_any(module_flags) and 'users' not in menus and 'locked_accounts' not in menus:
            continue

        changed = False
        users_flags = _flags(menus.get('users')) if 'users' in menus else module_flags
        if 'users' not in menus and _has_any(users_flags):
            menus['users'] = users_flags
            changed = True
        if 'locked_accounts' not in menus:
            source = menus.get('users') or module_flags
            locked_flags = _flags(source)
            if _has_any(locked_flags):
                menus['locked_accounts'] = locked_flags
                changed = True
        if not changed:
            continue
        hrm['menus'] = menus
        perms['hrm'] = hrm
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        hrm = dict(perms.get('hrm') or {})
        menus = dict(hrm.get('menus') or {}) if isinstance(hrm.get('menus'), dict) else {}
        if not menus:
            continue
        changed = False
        for key in NEW_MENU_KEYS:
            if key in menus:
                menus.pop(key)
                changed = True
        if not changed:
            continue
        if menus:
            hrm['menus'] = menus
        else:
            hrm.pop('menus', None)
        perms['hrm'] = hrm
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0095_seed_san_xuat_ie_approve_menu'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
