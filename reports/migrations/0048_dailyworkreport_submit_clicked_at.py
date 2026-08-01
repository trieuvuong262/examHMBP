from django.db import migrations, models
from django.db.models import F, Min


def backfill_submit_clicked_at(apps, schema_editor):
    """Giữ nguyên mốc hạn duyệt / hạn sửa, rồi đưa submitted_at ca tối về giờ bắt đầu."""
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')

    DailyWorkReport.objects.filter(
        submitted_at__isnull=False,
        submit_clicked_at__isnull=True,
    ).update(submit_clicked_at=F('submitted_at'))

    night = (
        DailyWorkReport.objects.filter(
            report_profile='PRODUCTION',
            shift='NIGHT',
            submitted_at__isnull=False,
        )
        .annotate(first_step_started_at=Min('production_products__started_at'))
    )
    updates = []
    for report in night.iterator(chunk_size=500):
        started_at = report.first_step_started_at or report.shift_started_at
        if not started_at or started_at == report.submitted_at:
            continue
        report.submitted_at = started_at
        updates.append(report)
        if len(updates) >= 500:
            DailyWorkReport.objects.bulk_update(updates, ['submitted_at'])
            updates = []
    if updates:
        DailyWorkReport.objects.bulk_update(updates, ['submitted_at'])


def restore_submitted_at(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    DailyWorkReport.objects.filter(submit_clicked_at__isnull=False).update(
        submitted_at=F('submit_clicked_at')
    )


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0047_reportsgeneralsettings_allow_edit_wrong_stage_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyworkreport',
            name='submit_clicked_at',
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    'Thời điểm thật báo cáo chuyển sang Đã gửi. Ca tối hiển thị submitted_at '
                    'theo lúc bắt đầu công đoạn đầu tiên, nên hạn duyệt / hạn sửa tính theo '
                    'trường này.'
                ),
                null=True,
                verbose_name='Bấm gửi lúc',
            ),
        ),
        migrations.RunPython(backfill_submit_clicked_at, restore_submitted_at),
    ]
