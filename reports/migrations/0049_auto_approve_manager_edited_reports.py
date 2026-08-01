from django.db import migrations, models
from django.utils import timezone


def approve_manager_edited_reports(apps, schema_editor):
    """Duyệt bù báo cáo SX quản lý đã sửa nhưng treo lại.

    Phần lớn đã bị cron đẩy sang «Không duyệt» vì quá hạn, nên gỡ luôn cờ đó.
    """
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')

    now = timezone.now()
    pending = (
        DailyWorkReport.objects.filter(
            report_profile='PRODUCTION',
            status='SUBMITTED',
            hod_reviewed=False,
            production_products__updated_by__isnull=False,
        )
        .distinct()
        .values_list('pk', 'hod_first_reviewed_at')
    )
    first_review_missing = []
    all_ids = []
    for pk, first_reviewed_at in pending:
        all_ids.append(pk)
        if not first_reviewed_at:
            first_review_missing.append(pk)
    if not all_ids:
        return

    DailyWorkReport.objects.filter(pk__in=all_ids).update(
        hod_reviewed=True,
        hod_reviewed_at=now,
        hod_rejected=False,
        hod_rejected_at=None,
        updated_at=now,
    )
    if first_review_missing:
        DailyWorkReport.objects.filter(pk__in=first_review_missing).update(
            hod_first_reviewed_at=now
        )


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0048_dailyworkreport_submit_clicked_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='auto_approve_manager_edited_reports',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Quản lý / tổ trưởng sửa, thêm, xóa công đoạn hoặc thời gian làm việc — '
                    'báo cáo chuyển sang Đã duyệt.'
                ),
                verbose_name='Tự duyệt khi quản lý sửa báo cáo đã nộp',
            ),
        ),
        migrations.RunPython(
            approve_manager_edited_reports,
            migrations.RunPython.noop,
        ),
    ]
