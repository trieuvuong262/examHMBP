from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('audit', '0005_alter_useractivitylog_ip_address'),
    ]

    operations = [
        migrations.CreateModel(
            name='PortalBackupJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trigger', models.CharField(choices=[('manual', 'Thủ công'), ('scheduled', 'Tự động')], default='scheduled', max_length=16)),
                ('status', models.CharField(choices=[('pending', 'Chờ'), ('running', 'Đang chạy'), ('success', 'Thành công'), ('failed', 'Thất bại')], db_index=True, default='pending', max_length=16)),
                ('remote_path', models.CharField(blank=True, max_length=500)),
                ('message', models.TextField(blank=True)),
                ('artifacts', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('started_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='portal_backup_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Backup Portal lên NAS',
                'verbose_name_plural': 'Backup Portal lên NAS',
                'ordering': ['-created_at'],
            },
        ),
    ]
