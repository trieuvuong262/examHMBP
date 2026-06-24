import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def migrate_legacy_reminders(apps, schema_editor):
    ScheduleReminder = apps.get_model('utilities', 'ScheduleReminder')
    ScheduleReminderPushLog = apps.get_model('utilities', 'ScheduleReminderPushLog')

    for reminder in ScheduleReminder.objects.all():
        remind_at = getattr(reminder, 'remind_at', None)
        if remind_at is None:
            continue
        local = timezone.localtime(remind_at)
        reminder.repeat_mode = 'once'
        reminder.weekdays = [local.isoweekday()]
        reminder.remind_time = local.time().replace(second=0, microsecond=0)
        reminder.once_date = local.date()
        reminder.save(
            update_fields=['repeat_mode', 'weekdays', 'remind_time', 'once_date'],
        )
        push_sent_at = getattr(reminder, 'push_sent_at', None)
        if push_sent_at:
            fire_date = timezone.localtime(push_sent_at).date()
            ScheduleReminderPushLog.objects.get_or_create(
                reminder=reminder,
                fire_date=fire_date,
            )
            if reminder.once_date and reminder.once_date <= fire_date:
                reminder.is_active = False
                reminder.save(update_fields=['is_active'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('utilities', '0006_schedule_reminder'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduleReminderPushLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fire_date', models.DateField(verbose_name='Ngày gửi')),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Log push nhắc lịch',
                'verbose_name_plural': 'Log push nhắc lịch',
                'ordering': ['-sent_at'],
            },
        ),
        migrations.RemoveIndex(
            model_name='schedulereminder',
            name='util_sched_push_idx',
        ),
        migrations.AddField(
            model_name='schedulereminder',
            name='once_date',
            field=models.DateField(blank=True, null=True, verbose_name='Ngày nhắc (một lần)'),
        ),
        migrations.AddField(
            model_name='schedulereminder',
            name='remind_time',
            field=models.TimeField(default='09:00', verbose_name='Giờ nhắc'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='schedulereminder',
            name='repeat_mode',
            field=models.CharField(
                choices=[('once', 'Một lần'), ('weekly', 'Hàng tuần')],
                default='weekly',
                max_length=10,
                verbose_name='Kiểu nhắc',
            ),
        ),
        migrations.AddField(
            model_name='schedulereminder',
            name='weekdays',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='ISO weekday: 1=T2 … 7=CN',
                verbose_name='Các thứ trong tuần',
            ),
        ),
        migrations.RunPython(migrate_legacy_reminders, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='schedulereminder',
            name='push_sent_at',
        ),
        migrations.RemoveField(
            model_name='schedulereminder',
            name='remind_at',
        ),
        migrations.AddField(
            model_name='schedulereminderpushlog',
            name='reminder',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='push_logs',
                to='utilities.schedulereminder',
                verbose_name='Nhắc lịch',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='schedulereminderpushlog',
            unique_together={('reminder', 'fire_date')},
        ),
        migrations.AddIndex(
            model_name='schedulereminder',
            index=models.Index(fields=['is_active', 'repeat_mode'], name='util_sched_active_idx'),
        ),
        migrations.AlterModelOptions(
            name='schedulereminder',
            options={
                'ordering': ['remind_time', '-created_at'],
                'verbose_name': 'Nhắc lịch',
                'verbose_name_plural': 'Nhắc lịch',
            },
        ),
    ]
