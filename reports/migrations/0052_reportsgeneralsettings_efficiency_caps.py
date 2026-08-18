# Generated manually — ngưỡng hiệu suất thời gian / sản lượng cho báo cáo sai.

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0051_productionreportimageimport_employee_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='max_time_efficiency_pct',
            field=models.PositiveSmallIntegerField(
                default=200,
                help_text='Vượt mức này thì báo cáo sản xuất (báo cáo 1) bị coi là sai.',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(999),
                ],
                verbose_name='Hiệu suất thời gian tối đa',
            ),
        ),
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='max_quantity_efficiency_pct',
            field=models.PositiveSmallIntegerField(
                default=200,
                help_text='Vượt mức này thì báo cáo sản xuất (báo cáo 1) bị coi là sai.',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(999),
                ],
                verbose_name='Hiệu suất sản lượng tối đa',
            ),
        ),
    ]
