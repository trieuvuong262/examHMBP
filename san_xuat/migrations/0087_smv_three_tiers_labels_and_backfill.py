"""SMV 3 cấp: đổi verbose_name + backfill SMV sản phẩm trên OB.

- Thư viện: SxOperation.base_smv_min
- Sản phẩm: SxRoutingLine.applied_unit_smv (gợi ý từ library)
- Đơn hàng: SxSalesOrderRoutingLine.applied_unit_smv (baseline library_unit_smv = SMV sản phẩm)

Backfill: dòng OB có applied <= 0 và library > 0 → applied = library.
"""

from decimal import Decimal, ROUND_HALF_UP

import django.core.validators
from django.db import migrations, models


def _q(value, places='0.0001'):
    return Decimal(str(value or 0)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def backfill_product_smv(apps, schema_editor):
    SxRoutingLine = apps.get_model('san_xuat', 'SxRoutingLine')
    for line in SxRoutingLine.objects.all().iterator():
        library = line.library_unit_smv or Decimal('0')
        applied = line.applied_unit_smv or Decimal('0')
        if applied > 0 or library <= 0:
            continue
        applied = library
        qty = line.qty_per_garment or Decimal('0')
        total = _q(qty * applied)
        variance = Decimal('0')
        if library:
            variance = _q((applied - library) / library * Decimal('100'), '0.01')
        SxRoutingLine.objects.filter(pk=line.pk).update(
            applied_unit_smv=applied,
            total_operation_smv=total,
            smv_variance_pct=variance,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0086_fg_receipt_warehouse_backfill'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sxoperation',
            name='base_smv_min',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                help_text='SMV thư viện trên một đơn vị cơ sở, đơn vị giây.',
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                verbose_name='SMV thư viện (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxroutingline',
            name='library_unit_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                max_digits=10,
                verbose_name='SMV thư viện (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxroutingline',
            name='applied_unit_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                verbose_name='SMV sản phẩm (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxroutingline',
            name='total_operation_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                help_text='SL/SP × SMV sản phẩm.',
                max_digits=12,
                verbose_name='Tổng SMV',
            ),
        ),
        migrations.AlterField(
            model_name='sxsalesorderroutingline',
            name='library_unit_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                help_text='Baseline từ OB (SMV sản phẩm), dùng so lệch với SMV đơn hàng.',
                max_digits=10,
                verbose_name='SMV sản phẩm (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxsalesorderroutingline',
            name='applied_unit_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                verbose_name='SMV đơn hàng (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxsalesorderroutingline',
            name='total_operation_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                help_text='SL/SP × SMV đơn hàng.',
                max_digits=12,
                verbose_name='Tổng SMV',
            ),
        ),
        migrations.RunPython(backfill_product_smv, noop_reverse),
    ]
