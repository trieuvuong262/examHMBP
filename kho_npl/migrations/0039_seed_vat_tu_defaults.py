from django.db import migrations


def seed_vat_tu_defaults(apps, schema_editor):
    WarehouseLocation = apps.get_model('kho_npl', 'WarehouseLocation')
    MaterialCategory = apps.get_model('kho_npl', 'MaterialCategory')
    WarehouseLocation.objects.get_or_create(
        stock_domain='vat_tu',
        code='MAIN',
        defaults={
            'name': 'Kho vật tư chính',
            'is_active': True,
            'location_kind': 'stock',
        },
    )
    WarehouseLocation.objects.get_or_create(
        stock_domain='vat_tu',
        code='HUY',
        defaults={
            'name': 'Kho hủy vật tư',
            'is_active': True,
            'location_kind': 'scrap',
        },
    )
    MaterialCategory.objects.get_or_create(
        stock_domain='vat_tu',
        code='vat-tu',
        defaults={
            'name': 'Vật tư chung',
            'sort_order': 0,
            'is_active': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0038_stock_domain'),
    ]

    operations = [
        migrations.RunPython(seed_vat_tu_defaults, migrations.RunPython.noop),
    ]
