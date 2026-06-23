"""Sao chép quyền menu Cấu hình RustDesk sang Quét thiết bị IT (documents)."""

from django.db import migrations


def copy_equipment_scan_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        documents = dict(perms.get('documents') or {})
        documents_menus = dict(documents.get('menus') or {})
        if 'equipment_scan' in documents_menus:
            continue
        source = documents_menus.get('rustdesk_config')
        if not source:
            continue
        documents_menus['equipment_scan'] = dict(source)
        documents['menus'] = documents_menus
        if not documents.get('view'):
            documents['view'] = bool(source.get('view'))
        perms['documents'] = documents
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0046_sync_rustdesk_group_permissions'),
    ]

    operations = [
        migrations.RunPython(copy_equipment_scan_menu_perms, migrations.RunPython.noop),
    ]
