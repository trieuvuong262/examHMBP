"""Thêm quyền menu Zalo OA (audit) — copy từ kiotviet_sync / qa_assistant."""

from django.db import migrations


def sync_zalo_oa_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        audit = dict(perms.get('audit') or {})
        if not audit.get('view'):
            continue
        menus = dict(audit.get('menus') or {})
        if 'zalo_oa' in menus:
            continue
        source = (
            menus.get('kiotviet_sync')
            or menus.get('qa_assistant')
            or menus.get('nas_links')
            or menus.get('backup')
        )
        if isinstance(source, dict) and source:
            menus['zalo_oa'] = dict(source)
        else:
            can_manage = bool(
                audit.get('create')
                or audit.get('update')
                or audit.get('export')
            )
            menus['zalo_oa'] = {
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
        ('hrm', '0073_profile_phone'),
    ]

    operations = [
        migrations.RunPython(sync_zalo_oa_menu_perms, migrations.RunPython.noop),
    ]
