from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0036_productionshiftproduct_updated_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyworkreporteditlog',
            name='detail',
            field=models.TextField(blank=True, verbose_name='Chi tiết thay đổi'),
        ),
    ]
