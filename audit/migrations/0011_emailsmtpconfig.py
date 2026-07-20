# Generated manually — EmailSmtpConfig

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('audit', '0010_rustdeskhost_mac_address'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailSmtpConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=False, verbose_name='Bật SMTP')),
                ('host', models.CharField(blank=True, default='', max_length=255, verbose_name='SMTP host')),
                ('port', models.PositiveIntegerField(default=587, verbose_name='Cổng')),
                ('username', models.CharField(blank=True, default='', max_length=255, verbose_name='Tài khoản SMTP')),
                ('password', models.CharField(blank=True, default='', max_length=255, verbose_name='Mật khẩu SMTP')),
                ('use_tls', models.BooleanField(default=True, verbose_name='TLS')),
                ('use_ssl', models.BooleanField(default=False, verbose_name='SSL')),
                ('from_email', models.CharField(
                    blank=True,
                    default='',
                    help_text='Ví dụ: noreply@justplay.vn hoặc JustPlay Portal <noreply@justplay.vn>',
                    max_length=255,
                    verbose_name='Email gửi đi (From)',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='email_smtp_configs_updated',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Cập nhật bởi',
                )),
            ],
            options={
                'verbose_name': 'Cấu hình SMTP email',
                'verbose_name_plural': 'Cấu hình SMTP email',
            },
        ),
    ]
