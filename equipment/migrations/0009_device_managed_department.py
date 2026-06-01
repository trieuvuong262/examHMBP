import django.db.models.deletion
from django.db import migrations, models


def migrate_managed_by_to_department(apps, schema_editor):
    Device = apps.get_model('equipment', 'Device')
    Department = apps.get_model('hrm', 'Department')

    def ensure_dept(name):
        dept, _ = Department.objects.get_or_create(
            name=name,
            defaults={'is_active': True, 'sort_order': 0},
        )
        return dept

    it_dept = (
        Department.objects.filter(name__icontains='CNTT').first()
        or Department.objects.filter(name__icontains='IT').first()
        or ensure_dept('IT / CNTT')
    )
    maint_dept = (
        Department.objects.filter(name__icontains='Bảo trì').first()
        or ensure_dept('Bảo trì xưởng')
    )

    for device in Device.objects.all().iterator():
        managed_by = getattr(device, 'managed_by', None)
        if managed_by == 'MAINTENANCE':
            device.managed_department_id = maint_dept.pk
        else:
            device.managed_department_id = it_dept.pk
        device.save(update_fields=['managed_department_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0031_split_service_requests_modules'),
        ('equipment', '0008_deviceupdatelog'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='managed_department',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='managed_equipment',
                to='hrm.department',
                verbose_name='Bộ phận quản lý',
            ),
        ),
        migrations.RunPython(migrate_managed_by_to_department, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='device',
            name='managed_by',
        ),
    ]
