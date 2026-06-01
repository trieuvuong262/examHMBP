import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('equipment', '0007_device_device_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceUpdateLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('create', 'Tạo mới'), ('update', 'Cập nhật')], default='update', max_length=20)),
                ('summary', models.TextField(verbose_name='Nội dung thay đổi')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='equipment_update_logs', to=settings.AUTH_USER_MODEL, verbose_name='Người cập nhật')),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='update_logs', to='equipment.device')),
            ],
            options={
                'verbose_name': 'Lịch sử cập nhật thiết bị',
                'verbose_name_plural': 'Lịch sử cập nhật thiết bị',
                'ordering': ['-created_at'],
            },
        ),
    ]
