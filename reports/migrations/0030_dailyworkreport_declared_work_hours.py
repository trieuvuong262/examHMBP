from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0029_dailyworkreport_hod_reviewed_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyworkreport',
            name='declared_work_hours',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=4,
                null=True,
                verbose_name='Thời gian làm việc (giờ)',
            ),
        ),
    ]
