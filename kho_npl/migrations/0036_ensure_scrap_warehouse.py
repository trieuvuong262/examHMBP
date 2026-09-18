from django.db import migrations

from kho_npl.choices import WAREHOUSE_SCRAP_CODE


def ensure_scrap_warehouse(apps, schema_editor):
    WarehouseLocation = apps.get_model('kho_npl', 'WarehouseLocation')
    location, created = WarehouseLocation.objects.get_or_create(
        code=WAREHOUSE_SCRAP_CODE,
        defaults={
            'name': 'Kho hủy',
            'is_active': True,
            'location_kind': 'scrap',
        },
    )
    if created:
        return
    update_fields = []
    if not location.is_active:
        location.is_active = True
        update_fields.append('is_active')
    if getattr(location, 'location_kind', None) != 'scrap':
        location.location_kind = 'scrap'
        update_fields.append('location_kind')
    if not (location.name or '').strip():
        location.name = 'Kho hủy'
        update_fields.append('name')
    if update_fields:
        location.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0035_stockreservation_ref_khsx'),
    ]

    operations = [
        migrations.RunPython(ensure_scrap_warehouse, migrations.RunPython.noop),
    ]
