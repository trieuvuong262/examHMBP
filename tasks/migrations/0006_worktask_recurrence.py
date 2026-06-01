from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tasks', '0005_worktask_skip_completion_review'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkTaskRecurrence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Tiêu đề')),
                ('description', models.TextField(blank=True, verbose_name='Mô tả')),
                ('task_type', models.CharField(choices=[('PRODUCTION', 'Sản xuất'), ('OFFICE', 'Văn phòng'), ('GENERAL', 'Chung')], default='GENERAL', max_length=20)),
                ('priority', models.CharField(choices=[('LOW', 'Thấp'), ('NORMAL', 'Bình thường'), ('HIGH', 'Cao'), ('URGENT', 'Khẩn cấp')], default='NORMAL', max_length=10)),
                ('skip_completion_review', models.BooleanField(default=False)),
                ('frequency', models.CharField(choices=[('daily', 'Hàng ngày'), ('weekly', 'Hàng tuần'), ('monthly', 'Hàng tháng')], default='weekly', max_length=10)),
                ('interval', models.PositiveSmallIntegerField(default=1, verbose_name='Mỗi N chu kỳ')),
                ('weekday', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Thứ trong tuần (0=Thứ Hai)')),
                ('day_of_month', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Ngày trong tháng')),
                ('due_offset_days', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Hạn sau N ngày kể từ ngày giao')),
                ('start_date', models.DateField(verbose_name='Ngày bắt đầu')),
                ('end_date', models.DateField(blank=True, null=True, verbose_name='Ngày kết thúc')),
                ('next_run_date', models.DateField(db_index=True, verbose_name='Lần giao tiếp theo')),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('last_generated_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assignee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recurring_work_tasks', to=settings.AUTH_USER_MODEL, verbose_name='Người nhận')),
                ('assigner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_task_recurrences', to=settings.AUTH_USER_MODEL, verbose_name='Người giao')),
            ],
            options={
                'verbose_name': 'Công việc lặp',
                'verbose_name_plural': 'Công việc lặp',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='WorkTaskRecurrenceAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='tasks/recurrence/%Y/%m/')),
                ('original_name', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('recurrence', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='tasks.worktaskrecurrence')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_task_recurrence_attachments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddField(
            model_name='worktask',
            name='recurrence',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='instances', to='tasks.worktaskrecurrence', verbose_name='Chu kỳ lặp'),
        ),
    ]
