from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('audit', '0007_userloginlock_iploginblock'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginSecurityConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wan_whitelist_ips', models.JSONField(blank=True, default=list)),
                ('ip_blacklist', models.JSONField(blank=True, default=list)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='login_security_configs_updated',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Cập nhật bởi',
                )),
            ],
            options={
                'verbose_name': 'Cấu hình bảo mật đăng nhập',
                'verbose_name_plural': 'Cấu hình bảo mật đăng nhập',
            },
        ),
    ]
