from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0069_techdocdesignfile_gallery'),
    ]

    operations = [
        migrations.AddField(
            model_name='bomversion',
            name='overhead_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Số tiền cố định / 1 SP — KHSH nhập tay.',
                max_digits=14,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                verbose_name='Chi phí sản xuất chung',
            ),
        ),
    ]
