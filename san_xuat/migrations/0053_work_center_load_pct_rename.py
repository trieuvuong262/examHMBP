from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0052_plan_route_kanban'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sxworkcenter',
            name='efficiency_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('100'),
                help_text=(
                    'Hệ số năng lực tổ so với bình thường: 80 = thiếu người, '
                    '100 = bình thường, 150 = tăng ca. Nhân vào quỹ phút hữu ích.'
                ),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0')),
                    django.core.validators.MaxValueValidator(Decimal('200')),
                ],
                verbose_name='Tải (%)',
            ),
        ),
        migrations.AlterField(
            model_name='sxgeneralsettings',
            name='capacity_load_warn_pct',
            field=models.PositiveSmallIntegerField(
                default=80,
                verbose_name='Ngưỡng cảnh báo lấp đầy (%)',
            ),
        ),
        migrations.AlterField(
            model_name='sxgeneralsettings',
            name='capacity_load_danger_pct',
            field=models.PositiveSmallIntegerField(
                default=100,
                verbose_name='Ngưỡng quá lấp đầy (%)',
            ),
        ),
    ]
