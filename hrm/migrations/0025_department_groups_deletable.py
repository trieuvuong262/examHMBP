from django.db import migrations


def allow_delete_department_groups(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    PermissionGroup.objects.exclude(slug__startswith='mac-dinh-').update(is_system=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0024_department_permission_groups'),
    ]

    operations = [
        migrations.RunPython(allow_delete_department_groups, noop),
    ]
