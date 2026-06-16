# Generated manually for DeviceStatus + Device.photo

from django.db import migrations, models


def seed_device_statuses(apps, schema_editor):
    DeviceStatus = apps.get_model('equipment', 'DeviceStatus')
    seeds = [
        ('new', 'Mới lắp', 0, True, True),
        ('active', 'Đang hoạt động', 10, True, True),
        ('broken', 'Đang hỏng', 20, True, True),
        ('maintenance', 'Đang bảo trì', 30, True, True),
        ('scrapped', 'Đã hủy / Thanh lý', 40, True, True),
    ]
    for code, name, sort_order, is_active, is_system in seeds:
        DeviceStatus.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'sort_order': sort_order,
                'is_active': is_active,
                'is_system': is_system,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0012_device_windows_fields_remove_is_online'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='Mã trạng thái')),
                ('name', models.CharField(max_length=100, verbose_name='Tên hiển thị')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
                ('is_system', models.BooleanField(default=False, verbose_name='Trạng thái hệ thống')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Trạng thái thiết bị',
                'verbose_name_plural': 'Trạng thái thiết bị',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddField(
            model_name='device',
            name='photo',
            field=models.ImageField(blank=True, null=True, upload_to='equipment/photos/', verbose_name='Hình ảnh thiết bị'),
        ),
        migrations.RunPython(seed_device_statuses, migrations.RunPython.noop),
    ]
