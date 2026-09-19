from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('training', '0006_lesson_duration_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lesson',
            name='lesson_type',
            field=models.CharField(
                choices=[
                    ('video', 'Video bài giảng'),
                    ('pdf', 'Tài liệu PDF'),
                    ('reading', 'Bài viết/Văn bản'),
                ],
                default='video',
                max_length=20,
                verbose_name='Loại bài học',
            ),
        ),
    ]
