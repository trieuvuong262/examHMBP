from decimal import Decimal

from django.db import migrations
from django.db.models import Sum


def seed_opening_batches(apps, schema_editor):
    MaterialBatch = apps.get_model('kho_npl', 'MaterialBatch')
    StockBalance = apps.get_model('kho_npl', 'StockBalance')
    WarehouseLocation = apps.get_model('kho_npl', 'WarehouseLocation')

    # Khớp kho_npl.choices.WAREHOUSE_SCRAP_CODE (+ fallback seed cũ)
    scrap_ids = list(
        WarehouseLocation.objects.filter(code__in=['HUY', 'SCRAP']).values_list('pk', flat=True),
    )

    balances = StockBalance.objects.all()
    if scrap_ids:
        balances = balances.exclude(location_id__in=scrap_ids)

    totals = (
        balances.values('material_id')
        .annotate(total=Sum('quantity'))
        .filter(total__gt=0)
    )
    for row in totals:
        material_id = row['material_id']
        total = row['total'] or Decimal('0')
        if total <= 0:
            continue
        if MaterialBatch.objects.filter(material_id=material_id, code='TON-DAU').exists():
            continue
        MaterialBatch.objects.create(
            material_id=material_id,
            code='TON-DAU',
            unit_price=Decimal('0'),
            quantity=total,
            is_active=True,
        )


def unseed_opening_batches(apps, schema_editor):
    MaterialBatch = apps.get_model('kho_npl', 'MaterialBatch')
    MaterialBatch.objects.filter(code='TON-DAU').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0022_material_batch_and_prices'),
    ]

    operations = [
        migrations.RunPython(seed_opening_batches, unseed_opening_batches),
    ]
