"""Bật quyền xem Caro cho mọi nhóm quyền."""

from django.db import migrations

_SIBLING_MENUS = (
    'meal_ordering',
    'salary_advance',
    'schedule_reminder',
    'trip_schedule',
)


def _module_flags(utilities):
    if any(key in utilities for key in ('create', 'update', 'delete', 'export', 'print')):
        edit = bool(utilities.get('edit'))
        return {
            'view': bool(utilities.get('view') or edit),
            'create': bool(utilities.get('create')),
            'update': bool(utilities.get('update')),
            'delete': bool(utilities.get('delete')),
            'export': bool(utilities.get('export')),
            'print': bool(utilities.get('print')),
        }
    edit = bool(utilities.get('edit'))
    return {
        'view': bool(utilities.get('view') or edit),
        'create': edit,
        'update': edit,
        'delete': edit,
        'export': edit,
        'print': False,
    }


def seed_caro_menu(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        utilities = dict(perms.get('utilities') or {})
        menus = utilities.get('menus')
        if isinstance(menus, dict) and menus:
            menus = dict(menus)
        else:
            inherited = _module_flags(utilities)
            menus = {key: dict(inherited) for key in _SIBLING_MENUS}
        caro = dict(menus.get('caro') or {})
        caro['view'] = True
        menus['caro'] = caro
        utilities['menus'] = menus
        utilities['view'] = True
        perms['utilities'] = utilities
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0119_drop_handover_status_menu'),
    ]

    operations = [
        migrations.RunPython(seed_caro_menu, migrations.RunPython.noop),
    ]
