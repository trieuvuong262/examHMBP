from django.db import migrations


def add_feedback_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'feedback' not in modules:
            modules.append('feedback')
            perm.modules = modules
            perm.save(update_fields=['modules'])


def remove_feedback_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'feedback']
        perm.modules = modules
        perm.save(update_fields=['modules'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0029_add_equipment_module'),
    ]

    operations = [
        migrations.RunPython(add_feedback_module, remove_feedback_module),
    ]
