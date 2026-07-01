"""Đồng bộ nhóm cấp 1/cấp 2 và gán NPL từ nhóm cũ."""

from django.db import migrations


def sync_categories(apps, schema_editor):
    from kho_npl.material_category_catalog import sync_material_category_catalog

    sync_material_category_catalog(backfill=True)


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0018_material_colors_extended'),
    ]

    operations = [
        migrations.RunPython(sync_categories, migrations.RunPython.noop),
    ]
