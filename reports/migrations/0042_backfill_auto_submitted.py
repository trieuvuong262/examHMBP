# Backfill auto_submitted từ nhật ký «Hệ thống tự động gửi…»

from django.db import migrations


def forwards(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    DailyWorkReportEditLog = apps.get_model('reports', 'DailyWorkReportEditLog')
    report_ids = (
        DailyWorkReportEditLog.objects.filter(summary__icontains='tự động gửi')
        .values_list('report_id', flat=True)
        .distinct()
    )
    DailyWorkReport.objects.filter(pk__in=report_ids, status='SUBMITTED').update(
        auto_submitted=True,
    )


def backwards(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    DailyWorkReport.objects.filter(auto_submitted=True).update(auto_submitted=False)


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0041_dailyworkreport_auto_submitted'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
