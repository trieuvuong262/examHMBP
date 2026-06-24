import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('utilities', '0005_meal_order_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduleReminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=120, verbose_name='Tiêu đề')),
                ('body', models.TextField(blank=True, verbose_name='Nội dung')),
                ('remind_at', models.DateTimeField(db_index=True, verbose_name='Thời gian nhắc')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang bật')),
                ('push_sent_at', models.DateTimeField(blank=True, null=True, verbose_name='Đã gửi push lúc')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_reminders', to=settings.AUTH_USER_MODEL, verbose_name='Nhân viên')),
            ],
            options={
                'verbose_name': 'Nhắc lịch',
                'verbose_name_plural': 'Nhắc lịch',
                'ordering': ['remind_at', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='schedulereminder',
            index=models.Index(fields=['is_active', 'push_sent_at', 'remind_at'], name='util_sched_push_idx'),
        ),
    ]
