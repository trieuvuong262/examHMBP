"""Seed submenu KPI tháng / Tổng kết — kế thừa quyền module KPI hiện có."""

from django.db import migrations


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
        kpi = perms.get('kpi')
        if not isinstance(kpi, dict):
            continue
        menus = dict(kpi.get('menus') or {}) if isinstance(kpi.get('menus'), dict) else {}
        source = _flags(kpi)
        if not _has_any(source):
            continue
        changed = False
        if 'boards' not in menus:
            menus['boards'] = dict(source)
            changed = True
        if 'summary' not in menus:
            # Tổng kết: chỉ xem (báo cáo)
            menus['summary'] = {
                'view': bool(source.get('view')),
                'create': False,
                'update': False,
                'delete': False,
                'export': bool(source.get('export')),
                'print': False,
            }
            changed = True
        if not changed:
            continue
        kpi['menus'] = menus
        perms['kpi'] = kpi
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        kpi = perms.get('kpi')
        if not isinstance(kpi, dict):
            continue
        menus = dict(kpi.get('menus') or {}) if isinstance(kpi.get('menus'), dict) else {}
        removed = False
        for key in ('boards', 'summary'):
            if key in menus:
                menus.pop(key, None)
                removed = True
        if not removed:
            continue
        if menus:
            kpi['menus'] = menus
        else:
            kpi.pop('menus', None)
        perms['kpi'] = kpi
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0101_restore_kpi_module'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
