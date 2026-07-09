from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0035_dailyworkreporteditlog_resubmit_action'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionshiftproduct',
            name='updated_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='production_products_updated',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Cập nhật bởi',
            ),
        ),
    ]
