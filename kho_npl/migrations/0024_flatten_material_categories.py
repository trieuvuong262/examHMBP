from django.db import migrations


def flatten_categories(apps, schema_editor):
    Material = apps.get_model('kho_npl', 'Material')
    MaterialCategory = apps.get_model('kho_npl', 'MaterialCategory')

    parent_ids = list(
        MaterialCategory.objects.filter(children__isnull=False)
        .values_list('pk', flat=True)
        .distinct()
    )

    # Các nhóm con hiện tại trở thành nhóm phẳng.
    MaterialCategory.objects.filter(parent_id__isnull=False).update(parent_id=None)

    # Nhóm cha chỉ dùng để gom cây cũ và không gắn NPL sẽ được loại bỏ.
    used_ids = set(Material.objects.values_list('category_id', flat=True))
    removable_ids = [pk for pk in parent_ids if pk not in used_ids]
    MaterialCategory.objects.filter(pk__in=removable_ids).delete()


class Migration(migrations.Migration):
    # PostgreSQL không cho ALTER TABLE khi transaction còn pending FK trigger
    # từ bước cập nhật/xóa dữ liệu ngay trước đó.
    atomic = False

    dependencies = [
        ('kho_npl', '0023_seed_opening_batches'),
    ]

    operations = [
        migrations.RunPython(flatten_categories, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='materialcategory',
            name='parent',
        ),
    ]
