from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0028_alter_report_admin_labels'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyworkreport',
            name='hod_reviewed_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='HOD duyệt lúc',
            ),
        ),
        migrations.AlterField(
            model_name='dailyworkreport',
            name='hod_reviewed',
            field=models.BooleanField(default=False, verbose_name='HOD đã duyệt'),
        ),
    ]
