# Generated manually for FileScanConfig.allowed_extensions

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0013_filescanconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='filescanconfig',
            name='allowed_extensions',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Danh sách phần mở rộng (có dấu chấm). Để trống để dùng danh sách mặc định trong mã.',
                verbose_name='Định dạng được phép',
            ),
        ),
    ]
