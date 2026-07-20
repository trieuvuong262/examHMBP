# Generated manually — EmailSmtpConfig.ssl_verify

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0011_emailsmtpconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailsmtpconfig',
            name='ssl_verify',
            field=models.BooleanField(
                default=True,
                help_text='Tắt nếu mail nội bộ bị Hostname mismatch / self-signed.',
                verbose_name='Xác minh chứng chỉ SSL',
            ),
        ),
    ]
