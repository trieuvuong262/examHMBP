"""Thêm quyền menu Email (audit) — copy từ zalo_oa / qa_assistant."""

from django.db import migrations


def sync_email_config_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        audit = dict(perms.get('audit') or {})
        if not audit.get('view'):
            continue
        menus = dict(audit.get('menus') or {})
        if 'email_config' in menus:
            continue
        source = (
            menus.get('zalo_oa')
            or menus.get('qa_assistant')
            or menus.get('kiotviet_sync')
            or menus.get('backup')
        )
        if isinstance(source, dict) and source:
            menus['email_config'] = dict(source)
        else:
            can_manage = bool(
                audit.get('create')
                or audit.get('update')
                or audit.get('export')
            )
            menus['email_config'] = {
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
        ('hrm', '0074_sync_zalo_oa_menu_perm'),
    ]

    operations = [
        migrations.RunPython(sync_email_config_menu_perms, migrations.RunPython.noop),
    ]
