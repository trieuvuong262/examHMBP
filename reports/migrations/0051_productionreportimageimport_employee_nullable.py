# Generated manually for AI worker auto-match from photo.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0050_productionreportimageimport'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='productionreportimageimport',
            name='employee',
            field=models.ForeignKey(
                blank=True,
                help_text='Có thể để trống tạm khi AI chưa khớp được công nhân từ ảnh.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='production_report_image_imports',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Nhân viên',
            ),
        ),
    ]
