"""Chuyển menu Tải bộ cài sang Thư viện — giữ quyền tải cho mọi nhóm đã duyệt NAS."""

from django.db import migrations

VIEW = {'view': True, 'create': False, 'update': False, 'delete': False, 'export': False}


def move_nas_download_to_documents(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        nas = dict(perms.get('nas_storage') or {})
        nas_menus = nas.get('menus')
        if not isinstance(nas_menus, dict):
            nas_menus = {}
        else:
            nas_menus = dict(nas_menus)

        documents = dict(perms.get('documents') or {})
        docs_menus = documents.get('menus')
        if not isinstance(docs_menus, dict):
            docs_menus = {}
        else:
            docs_menus = dict(docs_menus)

        nas_dl = nas_menus.get('nas_download')
        nas_browse = nas_menus.get('browse')
        had_nas_download_access = bool(
            nas.get('view') and (nas_dl or nas_browse or docs_menus.get('nas_download'))
        )
        if not had_nas_download_access and not docs_menus.get('nas_download'):
            continue

        source = docs_menus.get('nas_download') or nas_dl or nas_browse
        if not isinstance(source, dict) or not source:
            source = dict(VIEW)
        else:
            source = dict(source)

        if 'nas_download' not in docs_menus:
            docs_menus['nas_download'] = source
            documents['menus'] = docs_menus

        if had_nas_download_access and not documents.get('view'):
            documents['view'] = True

        if 'nas_download' in nas_menus:
            del nas_menus['nas_download']
            nas['menus'] = nas_menus
            perms['nas_storage'] = nas

        perms['documents'] = documents
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0057_nas_download_under_nas_storage'),
    ]

    operations = [
        migrations.RunPython(move_nas_download_to_documents, migrations.RunPython.noop),
    ]
