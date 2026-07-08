from django.db import migrations, models
from django.db.models import F


def backfill_hod_first_reviewed_at(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    DailyWorkReport.objects.filter(
        hod_reviewed_at__isnull=False,
        hod_first_reviewed_at__isnull=True,
    ).update(hod_first_reviewed_at=F('hod_reviewed_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0031_dailyworkreport_hod_rejected'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyworkreport',
            name='hod_first_reviewed_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Lần duyệt đầu tiên lúc',
            ),
        ),
        migrations.RunPython(backfill_hod_first_reviewed_at, migrations.RunPython.noop),
    ]
