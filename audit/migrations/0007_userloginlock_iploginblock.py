import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('audit', '0006_portalbackupjob'),
    ]

    operations = [
        migrations.CreateModel(
            name='IpLoginBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(db_index=True, unique=True)),
                ('failed_attempts', models.PositiveIntegerField(default=0)),
                ('unknown_username_count', models.PositiveIntegerField(default=0)),
                ('sample_usernames', models.JSONField(blank=True, default=list)),
                ('blocked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('last_failed_at', models.DateTimeField(blank=True, null=True)),
                ('unlocked_at', models.DateTimeField(blank=True, null=True)),
                ('unlocked_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ip_blocks_cleared',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='IT bỏ chặn',
                )),
            ],
            options={
                'verbose_name': 'Chặn IP đăng nhập',
                'verbose_name_plural': 'Chặn IP đăng nhập',
            },
        ),
        migrations.CreateModel(
            name='UserLoginLock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username_snapshot', models.CharField(blank=True, db_index=True, max_length=150)),
                ('failed_attempts', models.PositiveSmallIntegerField(default=0)),
                ('locked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('last_failed_at', models.DateTimeField(blank=True, null=True)),
                ('last_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('unlocked_at', models.DateTimeField(blank=True, null=True)),
                ('unlocked_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='login_locks_unlocked',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='IT mở khóa',
                )),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='login_lock',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Tài khoản',
                )),
            ],
            options={
                'verbose_name': 'Khóa đăng nhập tài khoản',
                'verbose_name_plural': 'Khóa đăng nhập tài khoản',
            },
        ),
    ]
