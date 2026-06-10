from django.db import migrations

from kho_npl.choices import DEFAULT_MATERIAL_CATEGORIES


def seed_master_data(apps, schema_editor):
    MaterialCategory = apps.get_model('kho_npl', 'MaterialCategory')
    Unit = apps.get_model('kho_npl', 'Unit')
    WarehouseLocation = apps.get_model('kho_npl', 'WarehouseLocation')

    for code, name, sort_order in DEFAULT_MATERIAL_CATEGORIES:
        MaterialCategory.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': sort_order, 'is_active': True},
        )

    default_units = [
        ('met', 'Mét'),
        ('cuon', 'Cuộn'),
        ('cai', 'Cái'),
        ('bo', 'Bộ'),
        ('kg', 'Kg'),
        ('goi', 'Gói'),
    ]
    for code, name in default_units:
        Unit.objects.get_or_create(code=code, defaults={'name': name, 'is_active': True})

    WarehouseLocation.objects.get_or_create(
        code='MAIN',
        defaults={'name': 'Kho chính', 'is_active': True},
    )


def unseed_master_data(apps, schema_editor):
    MaterialCategory = apps.get_model('kho_npl', 'MaterialCategory')
    Unit = apps.get_model('kho_npl', 'Unit')
    WarehouseLocation = apps.get_model('kho_npl', 'WarehouseLocation')

    MaterialCategory.objects.filter(
        code__in=[code for code, _, _ in DEFAULT_MATERIAL_CATEGORIES],
    ).delete()
    Unit.objects.filter(code__in=['met', 'cuon', 'cai', 'bo', 'kg', 'goi']).delete()
    WarehouseLocation.objects.filter(code='MAIN').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_master_data, unseed_master_data),
    ]
