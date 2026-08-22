"""Thời gian kiểm đếm + vận chuyển giữa các công đoạn (chỉnh được)."""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0087_smv_three_tiers_labels_and_backfill'),
    ]

    operations = [
        migrations.AddField(
            model_name='processstep',
            name='count_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Kiểm đếm (phút)',
            ),
        ),
        migrations.AddField(
            model_name='processstep',
            name='transfer_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Vận chuyển (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxroutingline',
            name='count_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Kiểm đếm (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxroutingline',
            name='transfer_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Vận chuyển (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorderroutingline',
            name='count_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Kiểm đếm (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorderroutingline',
            name='transfer_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Vận chuyển (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorderplanstep',
            name='count_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Kiểm đếm (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorderplanstep',
            name='transfer_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Vận chuyển (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxmoprocessstep',
            name='count_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Kiểm đếm (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxmoprocessstep',
            name='transfer_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Vận chuyển (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='plan_count_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Kiểm đếm mặc định giữa công đoạn (phút)',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='plan_transfer_minutes',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
                verbose_name='Vận chuyển mặc định giữa công đoạn (phút)',
            ),
        ),
    ]
