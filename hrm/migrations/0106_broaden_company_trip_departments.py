from django.db import migrations


def broaden_company_trip_departments(apps, schema_editor):
    """1A — mọi phòng ban được bật module company_trip để NV active đăng ký được."""
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'company_trip' not in modules:
            modules.append('company_trip')
            perm.modules = modules
            perm.save(update_fields=['modules'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0105_add_company_trip_module'),
    ]

    operations = [
        migrations.RunPython(broaden_company_trip_departments, noop),
    ]
