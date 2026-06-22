from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0013_devicestatus_device_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='rustdesk_id',
            field=models.CharField(blank=True, max_length=20, verbose_name='RustDesk ID'),
        ),
        migrations.AddField(
            model_name='device',
            name='rustdesk_password',
            field=models.CharField(blank=True, max_length=128, verbose_name='RustDesk mật khẩu'),
        ),
    ]
