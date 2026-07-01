"""Đồng bộ lại bảng màu NPL và gán màu cho NPL thiếu."""

from django.db import migrations


def resync_material_colors(apps, schema_editor):
    from kho_npl.material_color_catalog import backfill_material_colors, ensure_material_colors

    ensure_material_colors()
    backfill_material_colors(only_missing=True)


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0016_resync_material_category_tree'),
    ]

    operations = [
        migrations.RunPython(resync_material_colors, migrations.RunPython.noop),
    ]
