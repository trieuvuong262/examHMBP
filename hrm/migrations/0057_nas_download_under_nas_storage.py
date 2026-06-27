"""Chuyển menu Tải NAS sang module NAS — mọi nhóm có quyền duyệt NAS."""

from django.db import migrations

VIEW = {'view': True, 'create': False, 'update': False, 'delete': False, 'export': False}


def sync_nas_download_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        nas = dict(perms.get('nas_storage') or {})
        if not nas.get('view'):
            continue
        menus = nas.get('menus')
        if not isinstance(menus, dict):
            continue
        if 'nas_download' in menus:
            continue
        source = menus.get('browse')
        if not source:
            documents = dict(perms.get('documents') or {})
            docs_menus = documents.get('menus') or {}
            if isinstance(docs_menus, dict):
                source = docs_menus.get('nas_download')
        menus = dict(menus)
        menus['nas_download'] = dict(source) if isinstance(source, dict) and source else dict(VIEW)
        nas['menus'] = menus
        perms['nas_storage'] = nas
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0056_nas_download_menu_perm'),
    ]

    operations = [
        migrations.RunPython(sync_nas_download_menu_perms, migrations.RunPython.noop),
    ]
