from django.db import migrations

from kho_san_pham.choices import KV_MAP_MATCH_EXACT


def add_street_ii_map(apps, schema_editor):
    ProductTypeKvMap = apps.get_model('kho_san_pham', 'ProductTypeKvMap')
    if ProductTypeKvMap.objects.filter(
        match_value__iexact='STREET II',
        match_mode=KV_MAP_MATCH_EXACT,
    ).exists():
        return
    street = (
        ProductTypeKvMap.objects.filter(
            match_value__iexact='STREET',
            match_mode=KV_MAP_MATCH_EXACT,
            is_active=True,
        )
        .order_by('priority', 'id')
        .first()
    )
    if street is None:
        return
    ProductTypeKvMap.objects.create(
        match_value='STREET II',
        match_mode=KV_MAP_MATCH_EXACT,
        product_type_id=street.product_type_id,
        priority=street.priority,
        is_active=True,
        notes='Cùng loại STREET — bộ bóng đá',
    )


def remove_street_ii_map(apps, schema_editor):
    ProductTypeKvMap = apps.get_model('kho_san_pham', 'ProductTypeKvMap')
    ProductTypeKvMap.objects.filter(
        match_value__iexact='STREET II',
        match_mode=KV_MAP_MATCH_EXACT,
        notes='Cùng loại STREET — bộ bóng đá',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0015_alter_stockledger_source_doc_type'),
    ]

    operations = [
        migrations.RunPython(add_street_ii_map, remove_street_ii_map),
    ]
