"""Đồng bộ lại cây nhóm NPL 2 cấp (cha + con) — sửa DB production thiếu nhóm cấp 1."""

from django.db import migrations


def resync_category_tree(apps, schema_editor):
    # Migration 0016 chạy trước 0038_stock_domain. Không import model/runtime
    # hiện tại ở đây vì model hiện tại đã yêu cầu cột stock_domain.
    MaterialCategory = apps.get_model('kho_npl', 'MaterialCategory')
    from kho_npl.choices import DEFAULT_MATERIAL_CATEGORIES

    for code, name, sort_order in DEFAULT_MATERIAL_CATEGORIES:
        MaterialCategory.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'sort_order': sort_order,
                'is_active': True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('kho_npl', '0015_disposal_line_location'),
    ]

    operations = [
        migrations.RunPython(resync_category_tree, migrations.RunPython.noop),
    ]


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0015_disposal_line_location'),
    ]

    operations = [
        migrations.RunPython(resync_category_tree, migrations.RunPython.noop),
    ]
