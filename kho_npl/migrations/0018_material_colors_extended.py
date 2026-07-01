"""Bổ sung màu nội bộ JustPlay và gán màu NPL còn thiếu."""

from django.db import migrations


def resync_material_colors_extended(apps, schema_editor):
    from kho_npl.material_color_catalog import backfill_material_colors, ensure_material_colors

    ensure_material_colors()
    backfill_material_colors(only_missing=True)


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0017_resync_material_colors'),
    ]

    operations = [
        migrations.RunPython(resync_material_colors_extended, migrations.RunPython.noop),
    ]
