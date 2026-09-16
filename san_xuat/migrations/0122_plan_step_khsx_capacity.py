from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0121_sxorderteamdayplan'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorderplanstep',
            name='khsx_headcount',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='Chỉnh trên kế hoạch SX để tính thời gian. Không đổi danh mục năng lực.',
                null=True,
                verbose_name='Số người (KHSX)',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorderplanstep',
            name='khsx_efficiency_pct',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Chỉnh trên kế hoạch SX để tính thời gian. Không đổi danh mục năng lực.',
                max_digits=5,
                null=True,
                validators=[
                    MinValueValidator(Decimal('0')),
                    MaxValueValidator(Decimal('200')),
                ],
                verbose_name='Hệ số tải KHSX (%)',
            ),
        ),
    ]
