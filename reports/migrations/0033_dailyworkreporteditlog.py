from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0032_dailyworkreport_hod_first_reviewed_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyWorkReportEditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('actor_kind', models.CharField(choices=[('employee', 'Nhân viên'), ('manager', 'Quản lý')], max_length=20, verbose_name='Vai trò')),
                ('action', models.CharField(choices=[('update', 'Chỉnh sửa'), ('submit', 'Gửi báo cáo')], default='update', max_length=20, verbose_name='Thao tác')),
                ('summary', models.CharField(blank=True, max_length=500, verbose_name='Mô tả')),
                ('edited_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Thời gian')),
                ('edited_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='report_edit_logs', to=settings.AUTH_USER_MODEL, verbose_name='Người sửa')),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='edit_logs', to='reports.dailyworkreport', verbose_name='Báo cáo')),
            ],
            options={
                'verbose_name': 'Lịch sử chỉnh sửa báo cáo',
                'verbose_name_plural': 'Lịch sử chỉnh sửa báo cáo',
                'ordering': ['-edited_at', '-id'],
                'indexes': [models.Index(fields=['report', '-edited_at'], name='reports_dai_report__a8f2c1_idx')],
            },
        ),
    ]
