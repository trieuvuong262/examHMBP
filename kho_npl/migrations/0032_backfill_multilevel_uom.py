from decimal import Decimal

from django.db import migrations


def _unique_code(Model, base):
    base = (base or 'quy-cach')[:40]
    code = base
    suffix = 2
    while Model.objects.filter(code=code).exists():
        tail = f'-{suffix}'
        code = f'{base[:40 - len(tail)]}{tail}'
        suffix += 1
    return code


def backfill_multilevel_uom(apps, schema_editor):
    Material = apps.get_model('kho_npl', 'Material')
    MaterialSpecification = apps.get_model('kho_npl', 'MaterialSpecification')
    Level = apps.get_model('kho_npl', 'MaterialSpecificationLevel')

    default_specs = {}

    def default_spec(unit):
        if unit.pk in default_specs:
            return default_specs[unit.pk]
        code = _unique_code(MaterialSpecification, f'dvt-{unit.code}')
        spec = MaterialSpecification.objects.create(
            code=code,
            name=f'ĐVT lẻ: {unit.name}',
            sort_order=0,
            is_active=True,
        )
        Level.objects.create(
            specification=spec,
            level=1,
            unit=unit,
            qty_in_next_lower=Decimal('1'),
        )
        default_specs[unit.pk] = spec
        return spec

    # Giữ quy cách chữ cũ và gắn cấp 1 theo ĐVT của các mã đang dùng.
    for spec in MaterialSpecification.objects.all():
        materials = Material.objects.filter(specification=spec).select_related('unit')
        unit_ids = list(materials.order_by().values_list('unit_id', flat=True).distinct())
        if not unit_ids:
            continue
        first_unit = materials.filter(unit_id=unit_ids[0]).first().unit
        Level.objects.get_or_create(
            specification=spec,
            level=1,
            defaults={'unit': first_unit, 'qty_in_next_lower': Decimal('1')},
        )
        for unit_id in unit_ids[1:]:
            sample = materials.filter(unit_id=unit_id).first()
            clone = MaterialSpecification.objects.create(
                code=_unique_code(MaterialSpecification, f'{spec.code}-{sample.unit.code}'),
                name=f'{spec.name} ({sample.unit.name})',
                sort_order=spec.sort_order,
                is_active=spec.is_active,
            )
            Level.objects.create(
                specification=clone,
                level=1,
                unit=sample.unit,
                qty_in_next_lower=Decimal('1'),
            )
            materials.filter(unit_id=unit_id).update(specification=clone)

    for material in Material.objects.filter(specification__isnull=True).select_related('unit'):
        material.specification = default_spec(material.unit)
        material.save(update_fields=['specification'])

    line_configs = (
        ('StockReceiptLine', 'received_qty'),
        ('StockIssueLine', 'quantity'),
        ('StockDisposalLine', 'quantity'),
        ('StockTransferLine', 'quantity'),
        ('StockAdjustmentLine', 'actual_qty'),
        ('StocktakeLine', 'actual_qty'),
    )
    for model_name, qty_field in line_configs:
        Line = apps.get_model('kho_npl', model_name)
        for line in Line.objects.select_related('material__unit').all().iterator():
            qty = getattr(line, qty_field)
            line.line_unit_id = line.material.unit_id
            line.uom_factor = Decimal('1')
            line.qty_base = qty
            line.save(update_fields=['line_unit', 'uom_factor', 'qty_base'])


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0031_stockadjustmentline_line_unit_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_multilevel_uom, migrations.RunPython.noop),
    ]
