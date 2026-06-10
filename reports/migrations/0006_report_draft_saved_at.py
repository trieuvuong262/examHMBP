from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0005_simplify_weekly_report'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyworkreport',
            name='draft_saved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Lưu nháp lúc'),
        ),
        migrations.AddField(
            model_name='weeklyworkreport',
            name='draft_saved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Lưu nháp lúc'),
        ),
    ]
