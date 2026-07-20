# Generated manually — PasswordResetOtp

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('zalo', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PasswordResetOtp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_hash', models.CharField(max_length=64)),
                ('session_token', models.CharField(db_index=True, max_length=64, unique=True)),
                ('phone', models.CharField(blank=True, default='', max_length=20)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Chờ xác thực'),
                        ('verified', 'Đã xác thực OTP'),
                        ('used', 'Đã đặt mật khẩu'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=16,
                )),
                ('expires_at', models.DateTimeField()),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='password_reset_otps',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'OTP quên mật khẩu',
                'verbose_name_plural': 'OTP quên mật khẩu',
                'ordering': ('-created_at',),
            },
        ),
        migrations.AddIndex(
            model_name='passwordresetotp',
            index=models.Index(fields=['user', 'created_at'], name='zalo_passwo_user_id_7f2a1c_idx'),
        ),
        migrations.AddIndex(
            model_name='passwordresetotp',
            index=models.Index(fields=['ip_address', 'created_at'], name='zalo_passwo_ip_addr_9c4e2b_idx'),
        ),
    ]
