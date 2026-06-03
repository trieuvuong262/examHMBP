from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0011_device_ultraviewer'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='windows_version',
            field=models.CharField(blank=True, max_length=200, verbose_name='Phiên bản Windows'),
        ),
        migrations.AddField(
            model_name='device',
            name='windows_license',
            field=models.CharField(blank=True, max_length=128, verbose_name='License Windows'),
        ),
        migrations.RemoveField(
            model_name='device',
            name='is_online',
        ),
    ]
