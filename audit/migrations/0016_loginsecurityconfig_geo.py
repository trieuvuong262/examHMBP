from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0015_filescanconfig_max_mb_limits'),
    ]

    operations = [
        migrations.AddField(
            model_name='loginsecurityconfig',
            name='geo_enabled',
            field=models.BooleanField(
                default=False,
                verbose_name='Chặn kết nối ngoài quốc gia cho phép',
            ),
        ),
        migrations.AddField(
            model_name='loginsecurityconfig',
            name='allowed_countries',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Mã ISO (VN). Để trống nghĩa là chỉ Việt Nam khi bật chặn.',
                verbose_name='Quốc gia được kết nối',
            ),
        ),
    ]
