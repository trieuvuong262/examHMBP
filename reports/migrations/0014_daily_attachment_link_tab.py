import os

from django.core.files.base import ContentFile
from django.db import migrations, models

from reports.report_profile import REPORT_PROFILE_OFFICE


def migrate_weekly_vp_attachments_to_daily(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    DailyWorkReportAttachment = apps.get_model('reports', 'DailyWorkReportAttachment')
    WeeklyWorkReport = apps.get_model('reports', 'WeeklyWorkReport')
    WeeklyWorkReportAttachment = apps.get_model('reports', 'WeeklyWorkReportAttachment')

    for weekly in WeeklyWorkReport.objects.filter(report_profile=REPORT_PROFILE_OFFICE):
        daily = DailyWorkReport.objects.filter(
            employee_id=weekly.employee_id,
            report_date=weekly.week_start,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
        ).first()
        if not daily:
            continue
        for watt in WeeklyWorkReportAttachment.objects.filter(report_id=weekly.pk):
            name = watt.original_name or os.path.basename(watt.file.name)
            if DailyWorkReportAttachment.objects.filter(
                report_id=daily.pk,
                source_tab='LINK',
                original_name=name,
            ).exists():
                continue
            watt.file.open('rb')
            try:
                content = watt.file.read()
            finally:
                watt.file.close()
            DailyWorkReportAttachment.objects.create(
                report_id=daily.pk,
                source_tab='LINK',
                kind=watt.kind,
                file=ContentFile(content, name=name),
                original_name=name,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0013_office_report_period_links'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dailyworkreportattachment',
            name='source_tab',
            field=models.CharField(
                choices=[
                    ('BANG', 'Bảng'),
                    ('VANBAN', 'Văn bản'),
                    ('LINK', 'Link'),
                ],
                max_length=10,
            ),
        ),
        migrations.RunPython(
            migrate_weekly_vp_attachments_to_daily,
            migrations.RunPython.noop,
        ),
    ]
