from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('training', '0005_lesson_video_url'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lesson',
            name='duration_estimate',
            field=models.IntegerField(default=30, verbose_name='Thời gian dự kiến (phút)'),
        ),
    ]
