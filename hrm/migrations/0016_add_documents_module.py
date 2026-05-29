from django.db import migrations


def add_documents_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'documents' not in modules:
            modules.append('documents')
            perm.modules = modules
            perm.save(update_fields=['modules'])


def remove_documents_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'documents']
        perm.modules = modules
        perm.save(update_fields=['modules'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0015_department_menu_permissions'),
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_documents_module, remove_documents_module),
    ]
