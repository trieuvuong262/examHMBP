"""Seed menu Thiết lập chung (general_settings) cho module reports."""

from django.db import migrations

NEW_MENU_KEYS = ('general_settings',)


def _seed(perms_dict):
    reports = dict(perms_dict.get('reports') or {})
    if not reports:
        return False, perms_dict
    menus = dict(reports.get('menus') or {})
    if not menus:
        return False, perms_dict

    source = (
        menus.get('daily_cn_detail')
        or menus.get('report_stats')
        or menus.get('daily_cn')
    )
    if isinstance(source, dict) and source:
        template = {
            'view': bool(source.get('view')),
            'create': bool(source.get('create')),
            'update': bool(source.get('update')),
            'delete': bool(source.get('delete')),
            'export': bool(source.get('export')),
        }
    else:
        template = {
            'view': bool(reports.get('view')),
            'create': bool(reports.get('create')),
            'update': bool(reports.get('update')),
            'delete': bool(reports.get('delete')),
            'export': bool(reports.get('export')),
        }

    changed = False
    for key in NEW_MENU_KEYS:
        if key not in menus:
            menus[key] = dict(template)
            changed = True
    if not changed:
        return False, perms_dict
    reports['menus'] = menus
    out = dict(perms_dict)
    out['reports'] = reports
    return True, out


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        changed, new_perms = _seed(perms)
        if changed:
            group.module_permissions = new_perms
            group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        reports = dict(perms.get('reports') or {})
        menus = dict(reports.get('menus') or {})
        if not menus:
            continue
        changed = False
        for key in NEW_MENU_KEYS:
            if key in menus:
                menus.pop(key)
                changed = True
        if changed:
            reports['menus'] = menus
            perms['reports'] = reports
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0078_seed_san_xuat_export_perm'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
