# SMV chuẩn/áp dụng: phút → giây (×60) trên thư viện, routing mã hàng, snapshot đơn, time study.

import django.core.validators
from decimal import Decimal
from django.db import migrations, models


def forwards_smv_to_seconds(apps, schema_editor):
    factor = Decimal('60')
    SxOperation = apps.get_model('san_xuat', 'SxOperation')
    SxRoutingLine = apps.get_model('san_xuat', 'SxRoutingLine')
    SxSalesOrderRoutingLine = apps.get_model('san_xuat', 'SxSalesOrderRoutingLine')
    SxTimeStudy = apps.get_model('san_xuat', 'SxTimeStudy')

    for op in SxOperation.objects.all().iterator():
        smv = op.base_smv_min or Decimal('0')
        if smv:
            op.base_smv_min = (smv * factor).quantize(Decimal('0.0001'))
            op.save(update_fields=['base_smv_min'])

    for line in SxRoutingLine.objects.all().iterator():
        lib = line.library_unit_smv or Decimal('0')
        applied = line.applied_unit_smv or Decimal('0')
        fields = []
        if lib:
            line.library_unit_smv = (lib * factor).quantize(Decimal('0.0001'))
            fields.append('library_unit_smv')
        if applied:
            line.applied_unit_smv = (applied * factor).quantize(Decimal('0.0001'))
            fields.append('applied_unit_smv')
        qty = line.qty_per_garment or Decimal('0')
        line.total_operation_smv = (
            qty * (line.applied_unit_smv or Decimal('0'))
        ).quantize(Decimal('0.0001'))
        fields.append('total_operation_smv')
        if fields:
            line.save(update_fields=fields)

    for line in SxSalesOrderRoutingLine.objects.all().iterator():
        lib = line.library_unit_smv or Decimal('0')
        applied = line.applied_unit_smv or Decimal('0')
        fields = []
        if lib:
            line.library_unit_smv = (lib * factor).quantize(Decimal('0.0001'))
            fields.append('library_unit_smv')
        if applied:
            line.applied_unit_smv = (applied * factor).quantize(Decimal('0.0001'))
            fields.append('applied_unit_smv')
        qty = line.qty_per_garment or Decimal('0')
        line.total_operation_smv = (
            qty * (line.applied_unit_smv or Decimal('0'))
        ).quantize(Decimal('0.0001'))
        fields.append('total_operation_smv')
        if fields:
            line.save(update_fields=fields)

    for study in SxTimeStudy.objects.all().iterator():
        fields = []
        cur = study.current_routing_smv or Decimal('0')
        calc = study.calculated_smv or Decimal('0')
        if cur:
            study.current_routing_smv = (cur * factor).quantize(Decimal('0.0001'))
            fields.append('current_routing_smv')
        if calc:
            study.calculated_smv = (calc * factor).quantize(Decimal('0.0001'))
            fields.append('calculated_smv')
        if fields:
            study.save(update_fields=fields)


def backwards_smv_to_minutes(apps, schema_editor):
    factor = Decimal('60')
    SxOperation = apps.get_model('san_xuat', 'SxOperation')
    SxRoutingLine = apps.get_model('san_xuat', 'SxRoutingLine')
    SxSalesOrderRoutingLine = apps.get_model('san_xuat', 'SxSalesOrderRoutingLine')
    SxTimeStudy = apps.get_model('san_xuat', 'SxTimeStudy')

    for op in SxOperation.objects.all().iterator():
        smv = op.base_smv_min or Decimal('0')
        if smv:
            op.base_smv_min = (smv / factor).quantize(Decimal('0.0001'))
            op.save(update_fields=['base_smv_min'])

    for line in SxRoutingLine.objects.all().iterator():
        lib = line.library_unit_smv or Decimal('0')
        applied = line.applied_unit_smv or Decimal('0')
        fields = []
        if lib:
            line.library_unit_smv = (lib / factor).quantize(Decimal('0.0001'))
            fields.append('library_unit_smv')
        if applied:
            line.applied_unit_smv = (applied / factor).quantize(Decimal('0.0001'))
            fields.append('applied_unit_smv')
        qty = line.qty_per_garment or Decimal('0')
        line.total_operation_smv = (
            qty * (line.applied_unit_smv or Decimal('0'))
        ).quantize(Decimal('0.0001'))
        fields.append('total_operation_smv')
        if fields:
            line.save(update_fields=fields)

    for line in SxSalesOrderRoutingLine.objects.all().iterator():
        lib = line.library_unit_smv or Decimal('0')
        applied = line.applied_unit_smv or Decimal('0')
        fields = []
        if lib:
            line.library_unit_smv = (lib / factor).quantize(Decimal('0.0001'))
            fields.append('library_unit_smv')
        if applied:
            line.applied_unit_smv = (applied / factor).quantize(Decimal('0.0001'))
            fields.append('applied_unit_smv')
        qty = line.qty_per_garment or Decimal('0')
        line.total_operation_smv = (
            qty * (line.applied_unit_smv or Decimal('0'))
        ).quantize(Decimal('0.0001'))
        fields.append('total_operation_smv')
        if fields:
            line.save(update_fields=fields)

    for study in SxTimeStudy.objects.all().iterator():
        fields = []
        cur = study.current_routing_smv or Decimal('0')
        calc = study.calculated_smv or Decimal('0')
        if cur:
            study.current_routing_smv = (cur / factor).quantize(Decimal('0.0001'))
            fields.append('current_routing_smv')
        if calc:
            study.calculated_smv = (calc / factor).quantize(Decimal('0.0001'))
            fields.append('calculated_smv')
        if fields:
            study.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0075_sxteampersonnelskill'),
    ]

    operations = [
        migrations.RunPython(forwards_smv_to_seconds, backwards_smv_to_minutes),
        migrations.AlterField(
            model_name='sxoperation',
            name='base_smv_min',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                help_text='SMV chuẩn trên một đơn vị cơ sở, đơn vị giây.',
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                verbose_name='SMV chuẩn (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxroutingline',
            name='library_unit_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                max_digits=10,
                verbose_name='SMV chuẩn (giây)',
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
                verbose_name='SMV áp dụng (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxsalesorderroutingline',
            name='library_unit_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                max_digits=10,
                verbose_name='SMV chuẩn (giây)',
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
                verbose_name='SMV áp dụng (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxtimestudy',
            name='current_routing_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                max_digits=10,
                verbose_name='SMV routing hiện tại (giây)',
            ),
        ),
        migrations.AlterField(
            model_name='sxtimestudy',
            name='calculated_smv',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('0'),
                max_digits=10,
                verbose_name='SMV tính toán (giây)',
            ),
        ),
    ]
