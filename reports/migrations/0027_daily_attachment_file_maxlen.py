from django.db import migrations, models

import reports.daily_nas_storage


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0026_reportcommentattachment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dailyworkreportattachment',
            name='file',
            field=models.FileField(
                max_length=255,
                storage=reports.daily_nas_storage.DailyReportNasStorage(),
                upload_to=reports.daily_nas_storage.daily_attachment_upload_to,
            ),
        ),
    ]
