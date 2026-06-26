"""Sao chép quyền menu Tài liệu sang Tải NAS (documents)."""

from django.db import migrations


def copy_nas_download_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        documents = dict(perms.get('documents') or {})
        documents_menus = dict(documents.get('menus') or {})
        if 'nas_download' in documents_menus:
            continue
        source = documents_menus.get('browse') or documents_menus.get('qa')
        if not source:
            if not documents.get('view'):
                continue
            source = {
                'view': bool(documents.get('view')),
                'create': bool(documents.get('create')),
                'update': bool(documents.get('update')),
                'delete': bool(documents.get('delete')),
                'export': bool(documents.get('export')),
            }
        documents_menus['nas_download'] = dict(source)
        documents['menus'] = documents_menus
        perms['documents'] = documents
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0055_profile_odoo_password_synced'),
    ]

    operations = [
        migrations.RunPython(copy_nas_download_menu_perms, migrations.RunPython.noop),
    ]
