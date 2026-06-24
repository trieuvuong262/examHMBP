"""Thêm quyền menu Giám sát NAS (audit) — copy từ vps_monitor."""

from django.db import migrations


def sync_nas_monitor_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        audit = dict(perms.get('audit') or {})
        if not audit.get('view'):
            continue
        menus = dict(audit.get('menus') or {})
        if 'nas_monitor' in menus:
            continue
        source = menus.get('vps_monitor') or menus.get('backup') or menus.get('nas_links')
        if isinstance(source, dict) and source:
            menus['nas_monitor'] = dict(source)
        else:
            can_manage = bool(
                audit.get('create')
                or audit.get('update')
                or audit.get('export')
            )
            menus['nas_monitor'] = {
                'view': True,
                'create': can_manage,
                'update': can_manage,
                'delete': bool(audit.get('delete')),
                'export': bool(audit.get('export')),
            }
        audit['menus'] = menus
        perms['audit'] = audit
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0050_sync_vps_monitor_menu_perm'),
    ]

    operations = [
        migrations.RunPython(sync_nas_monitor_menu_perms, migrations.RunPython.noop),
    ]
