from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('utilities', '0007_schedule_reminder_weekly'),
    ]

    operations = [
        migrations.CreateModel(
            name='PortalPushConsentLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('browser_permission', models.CharField(
                    choices=[('granted', 'Cho phép'), ('denied', 'Chặn'), ('default', 'Chưa chọn / bỏ qua')],
                    default='default',
                    max_length=16,
                    verbose_name='Quyền trình duyệt',
                )),
                ('push_subscribed', models.BooleanField(default=False, verbose_name='Đã đăng ký push thiết bị')),
                ('user_agent', models.CharField(blank=True, max_length=300, verbose_name='User-Agent')),
                ('consented_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='portal_push_consent',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Nhân viên',
                )),
            ],
            options={
                'verbose_name': 'Nhật ký đồng ý push portal',
                'verbose_name_plural': 'Nhật ký đồng ý push portal',
            },
        ),
    ]
