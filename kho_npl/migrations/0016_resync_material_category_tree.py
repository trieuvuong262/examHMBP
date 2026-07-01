"""Đồng bộ lại cây nhóm NPL 2 cấp (cha + con) — sửa DB production thiếu nhóm cấp 1."""

from django.db import migrations


def resync_category_tree(apps, schema_editor):
    from kho_npl.category_tree import ensure_material_category_tree

    ensure_material_category_tree()


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0015_disposal_line_location'),
    ]

    operations = [
        migrations.RunPython(resync_category_tree, migrations.RunPython.noop),
    ]
