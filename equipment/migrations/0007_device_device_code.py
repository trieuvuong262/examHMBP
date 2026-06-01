from django.db import migrations, models


def populate_device_codes(apps, schema_editor):
    Device = apps.get_model('equipment', 'Device')
    for index, device in enumerate(Device.objects.order_by('created_at'), start=1):
        if not device.device_code:
            device.device_code = f'TB-{index:06d}'
            device.save(update_fields=['device_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0006_devicecategory'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='device_code',
            field=models.CharField(
                blank=True,
                default='',
                max_length=50,
                verbose_name='Mã thiết bị',
            ),
        ),
        migrations.RunPython(populate_device_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='device',
            name='device_code',
            field=models.CharField(
                max_length=50,
                unique=True,
                verbose_name='Mã thiết bị',
            ),
        ),
    ]
