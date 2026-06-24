"""Thêm quyền menu Giám sát VPS (audit) — copy từ backup."""

from django.db import migrations


def sync_vps_monitor_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        audit = dict(perms.get('audit') or {})
        if not audit.get('view'):
            continue
        menus = dict(audit.get('menus') or {})
        if 'vps_monitor' in menus:
            continue
        source = menus.get('backup') or menus.get('nas_links') or menus.get('rustdesk')
        if isinstance(source, dict) and source:
            menus['vps_monitor'] = dict(source)
        else:
            can_manage = bool(
                audit.get('create')
                or audit.get('update')
                or audit.get('export')
            )
            menus['vps_monitor'] = {
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
        ('hrm', '0049_sync_schedule_reminder_menu_perm'),
    ]

    operations = [
        migrations.RunPython(sync_vps_monitor_menu_perms, migrations.RunPython.noop),
    ]
