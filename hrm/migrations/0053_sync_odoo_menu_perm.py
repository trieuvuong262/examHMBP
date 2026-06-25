"""Thêm quyền menu Odoo ERP (audit) — copy từ vps_monitor cho nhóm đã có giám sát."""

from django.db import migrations


def sync_odoo_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        audit = dict(perms.get('audit') or {})
        if not audit.get('view'):
            continue
        menus = dict(audit.get('menus') or {})
        if 'odoo' in menus:
            continue
        source = menus.get('vps_monitor') or menus.get('nas_monitor') or menus.get('backup')
        if isinstance(source, dict) and source:
            menus['odoo'] = dict(source)
        else:
            menus['odoo'] = {
                'view': False,
                'create': False,
                'update': False,
                'delete': False,
                'export': False,
            }
        audit['menus'] = menus
        perms['audit'] = audit
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0052_profile_odoo_user_id'),
    ]

    operations = [
        migrations.RunPython(sync_odoo_menu_perms, migrations.RunPython.noop),
    ]
