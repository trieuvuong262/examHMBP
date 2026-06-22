from django.db import migrations, models
import django.db.models.deletion


def migrate_device_rustdesk_to_hosts(apps, schema_editor):
    Device = apps.get_model('equipment', 'Device')
    RustDeskHost = apps.get_model('audit', 'RustDeskHost')
    for device in Device.objects.exclude(rustdesk_id='').iterator():
        rid = ''.join(c for c in (device.rustdesk_id or '') if c.isdigit())
        if not rid:
            continue
        RustDeskHost.objects.update_or_create(
            rustdesk_id=rid,
            defaults={
                'name': device.name or device.hostname or device.device_code or rid,
                'hostname': device.hostname or '',
                'ip_address': device.ip_address,
                'rustdesk_password': device.rustdesk_password or '',
                'department_text': device.usage_department_text or '',
                'assigned_user_text': device.assigned_user_text or '',
                'device_id': device.pk,
                'is_active': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0014_device_rustdesk'),
        ('audit', '0008_loginsecurityconfig'),
    ]

    operations = [
        migrations.CreateModel(
            name='RustDeskHost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Tên / mô tả')),
                ('hostname', models.CharField(blank=True, max_length=128, verbose_name='Hostname')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP')),
                ('rustdesk_id', models.CharField(max_length=20, unique=True, verbose_name='RustDesk ID')),
                ('rustdesk_password', models.CharField(blank=True, max_length=128, verbose_name='RustDesk mật khẩu')),
                ('department_text', models.CharField(blank=True, max_length=200, verbose_name='Phòng ban')),
                ('assigned_user_text', models.CharField(blank=True, max_length=200, verbose_name='Người dùng')),
                ('notes', models.TextField(blank=True, verbose_name='Ghi chú')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='rustdesk_hosts',
                    to='equipment.device',
                    verbose_name='Thiết bị IT liên kết',
                )),
            ],
            options={
                'verbose_name': 'Máy RustDesk',
                'verbose_name_plural': 'Máy RustDesk',
                'ordering': ['name', 'rustdesk_id'],
            },
        ),
        migrations.RunPython(migrate_device_rustdesk_to_hosts, migrations.RunPython.noop),
    ]
