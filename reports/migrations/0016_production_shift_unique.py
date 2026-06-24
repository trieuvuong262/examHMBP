from django.db import migrations, models


def migrate_shift_values(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    DailyWorkReport.objects.filter(shift='AFTERNOON').update(shift='OVERTIME')
    DailyWorkReport.objects.filter(
        report_profile='PRODUCTION',
        shift='',
    ).update(shift='MORNING')


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0015_production_hourly_damaged_note'),
    ]

    operations = [
        migrations.RunPython(migrate_shift_values, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='dailyworkreport',
            name='shift',
            field=models.CharField(
                blank=True,
                choices=[
                    ('MORNING', 'Ca sáng'),
                    ('OVERTIME', 'Tăng ca'),
                    ('NIGHT', 'Ca tối'),
                ],
                default='MORNING',
                max_length=20,
            ),
        ),
        migrations.AlterUniqueTogether(
            name='dailyworkreport',
            unique_together={('employee', 'report_date', 'report_profile', 'report_period', 'shift')},
        ),
    ]
