"""Sao chép quyền menu RustDesk (audit) sang Cấu hình RustDesk (documents)."""

from django.db import migrations


def copy_rustdesk_config_menu_perms(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        audit = perms.get('audit') or {}
        audit_menus = audit.get('menus') or {}
        rustdesk = audit_menus.get('rustdesk')
        if not rustdesk:
            continue
        documents = dict(perms.get('documents') or {})
        documents_menus = dict(documents.get('menus') or {})
        if 'rustdesk_config' in documents_menus:
            continue
        documents_menus['rustdesk_config'] = dict(rustdesk)
        documents['menus'] = documents_menus
        if not documents.get('view'):
            documents['view'] = bool(rustdesk.get('view'))
        perms['documents'] = documents
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0044_alter_userguide_body_and_more'),
    ]

    operations = [
        migrations.RunPython(copy_rustdesk_config_menu_perms, migrations.RunPython.noop),
    ]
