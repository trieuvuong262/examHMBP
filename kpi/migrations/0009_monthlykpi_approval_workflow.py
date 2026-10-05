from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kpi', '0008_monthlykpiitem_level_improve'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlykpi',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'NV đang tự đánh giá'),
                    ('self_submitted', 'Chờ quản lý chấm'),
                    ('mgr_reviewed', 'Chờ giám đốc phê duyệt'),
                    ('approved', 'Đã phê duyệt'),
                ],
                default='draft',
                max_length=20,
                verbose_name='Trạng thái duyệt',
            ),
        ),
        migrations.AddField(
            model_name='monthlykpi',
            name='self_submitted_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='NV nộp lúc'),
        ),
        migrations.AddField(
            model_name='monthlykpi',
            name='mgr_reviewed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='QL chấm lúc'),
        ),
        migrations.AddField(
            model_name='monthlykpi',
            name='approved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='approved_monthly_kpis',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Người phê duyệt',
            ),
        ),
        migrations.AddField(
            model_name='monthlykpi',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Phê duyệt lúc'),
        ),
    ]
