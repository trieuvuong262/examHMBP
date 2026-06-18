from django.db import migrations, models

from reports.report_profile import REPORT_PROFILE_OFFICE, get_report_profile


def backfill_weekly_report_profile(apps, schema_editor):
    WeeklyWorkReport = apps.get_model('reports', 'WeeklyWorkReport')
    for report in WeeklyWorkReport.objects.select_related('employee').iterator():
        profile = get_report_profile(report.employee)
        if report.report_profile != profile:
            report.report_profile = profile
            report.save(update_fields=['report_profile'])


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0010_production_slot_scope_zero_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='weeklyworkreport',
            name='report_profile',
            field=models.CharField(
                choices=[
                    ('PRODUCTION', 'Sản xuất (bảng năng suất)'),
                    ('OFFICE', 'Phòng ban khác (Excel / Word tự do)'),
                ],
                default=REPORT_PROFILE_OFFICE,
                max_length=20,
                verbose_name='Loại báo cáo',
            ),
        ),
        migrations.RunPython(backfill_weekly_report_profile, migrations.RunPython.noop),
    ]
