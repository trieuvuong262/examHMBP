from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('training', '0004_remove_lesson_video_url_lesson_video_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='lesson',
            name='video_url',
            field=models.URLField(
                blank=True,
                null=True,
                verbose_name='Link Video (YouTube/Vimeo)',
            ),
        ),
    ]
