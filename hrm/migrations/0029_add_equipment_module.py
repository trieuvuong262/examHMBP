from django.db import migrations


def add_equipment_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'equipment' not in modules:
            modules.append('equipment')
            perm.modules = modules
            perm.save(update_fields=['modules'])


def remove_equipment_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'equipment']
        perm.modules = modules
        perm.save(update_fields=['modules'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0028_nas_storage_upload_delete'),
        ('equipment', '0002_maintenancelog_service_request'),
    ]

    operations = [
        migrations.RunPython(add_equipment_module, remove_equipment_module),
    ]
