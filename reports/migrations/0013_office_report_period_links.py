from django.db import migrations, models

from reports.period_utils import PERIOD_DAY
from reports.report_profile import REPORT_PROFILE_OFFICE


def migrate_vp_weekly_to_daily(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    WeeklyWorkReport = apps.get_model('reports', 'WeeklyWorkReport')

    for weekly in WeeklyWorkReport.objects.filter(report_profile=REPORT_PROFILE_OFFICE):
        report, created = DailyWorkReport.objects.get_or_create(
            employee_id=weekly.employee_id,
            report_date=weekly.week_start,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            defaults={
                'links': weekly.links or '',
                'status': weekly.status,
                'submitted_at': weekly.submitted_at,
                'draft_saved_at': weekly.draft_saved_at,
                'hod_reviewed': weekly.hod_reviewed,
                'hod_note': weekly.hod_note or '',
                'shift': '',
            },
        )
        if not created and weekly.links and not report.links:
            report.links = weekly.links
            report.save(update_fields=['links'])


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0012_daily_work_report_attachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyworkreport',
            name='links',
            field=models.TextField(blank=True, verbose_name='Link (mỗi dòng một link)'),
        ),
        migrations.AddField(
            model_name='dailyworkreport',
            name='report_period',
            field=models.CharField(
                choices=[('day', 'Ngày'), ('week', 'Tuần'), ('month', 'Tháng')],
                default='day',
                max_length=10,
                verbose_name='Chu kỳ',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='dailyworkreport',
            unique_together={('employee', 'report_date', 'report_profile', 'report_period')},
        ),
        migrations.RunPython(migrate_vp_weekly_to_daily, migrations.RunPython.noop),
    ]
