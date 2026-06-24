"""Thêm quyền menu Nhắc lịch (utilities) cho các nhóm đã có Tiện ích."""

from django.db import migrations


def sync_schedule_reminder_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        utilities = dict(perms.get('utilities') or {})
        if not utilities.get('view'):
            continue
        menus = dict(utilities.get('menus') or {})
        if 'schedule_reminder' in menus:
            continue
        source = menus.get('meal_ordering') or menus.get('salary_advance')
        if isinstance(source, dict) and source:
            menus['schedule_reminder'] = dict(source)
        else:
            can_edit = bool(
                utilities.get('create')
                or utilities.get('update')
                or utilities.get('edit')
            )
            menus['schedule_reminder'] = {
                'view': True,
                'create': can_edit,
                'update': can_edit,
                'delete': bool(utilities.get('delete') or utilities.get('edit')),
            }
        utilities['menus'] = menus
        perms['utilities'] = utilities
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0048_sync_equipment_scan_group_permissions'),
    ]

    operations = [
        migrations.RunPython(sync_schedule_reminder_menu_perms, migrations.RunPython.noop),
    ]
