from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0030_dailyworkreport_declared_work_hours'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyworkreport',
            name='hod_rejected',
            field=models.BooleanField(default=False, verbose_name='Không duyệt (quá hạn)'),
        ),
        migrations.AddField(
            model_name='dailyworkreport',
            name='hod_rejected_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Không duyệt lúc'),
        ),
    ]
