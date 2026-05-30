from django.db import migrations


def enable_nas_upload_delete(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        nas = dict(perms.get('nas_storage') or {})
        if not nas.get('view'):
            continue
        nas['create'] = True
        nas['delete'] = True
        perms['nas_storage'] = nas
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0027_add_nas_storage_module'),
    ]

    operations = [
        migrations.RunPython(enable_nas_upload_delete, noop),
    ]
