# Generated manually — giới hạn dung lượng upload theo nhóm (MB)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0014_filescanconfig_allowed_extensions'),
    ]

    operations = [
        migrations.AddField(
            model_name='filescanconfig',
            name='max_mb_image',
            field=models.PositiveIntegerField(default=15, verbose_name='Ảnh tối đa (MB)'),
        ),
        migrations.AddField(
            model_name='filescanconfig',
            name='max_mb_doc',
            field=models.PositiveIntegerField(default=30, verbose_name='Tài liệu tối đa (MB)'),
        ),
        migrations.AddField(
            model_name='filescanconfig',
            name='max_mb_archive',
            field=models.PositiveIntegerField(default=50, verbose_name='File nén tối đa (MB)'),
        ),
        migrations.AddField(
            model_name='filescanconfig',
            name='max_mb_design',
            field=models.PositiveIntegerField(default=100, verbose_name='Thiết kế tối đa (MB)'),
        ),
        migrations.AddField(
            model_name='filescanconfig',
            name='max_mb_video',
            field=models.PositiveIntegerField(default=200, verbose_name='Video tối đa (MB)'),
        ),
    ]
