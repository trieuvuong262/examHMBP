from django.db import migrations, models
import django.db.models.deletion

from kho_npl.choices import DEFAULT_MATERIAL_CATEGORY_TREE


def build_category_tree(apps, schema_editor):
    MaterialCategory = apps.get_model('kho_npl', 'MaterialCategory')
    for parent_code, parent_name, parent_sort, children in DEFAULT_MATERIAL_CATEGORY_TREE:
        parent, _ = MaterialCategory.objects.get_or_create(
            code=parent_code,
            defaults={
                'name': parent_name,
                'sort_order': parent_sort,
                'is_active': True,
                'parent': None,
            },
        )
        if parent.name != parent_name or parent.sort_order != parent_sort or parent.parent_id:
            parent.name = parent_name
            parent.sort_order = parent_sort
            parent.parent = None
            parent.is_active = True
            parent.save()

        for child_code, child_name, child_sort in children:
            child = MaterialCategory.objects.filter(code=child_code).first()
            if child:
                child.parent_id = parent.pk
                child.name = child_name
                child.sort_order = child_sort
                child.is_active = True
                child.save(update_fields=['parent_id', 'name', 'sort_order', 'is_active'])
            else:
                MaterialCategory.objects.create(
                    code=child_code,
                    name=child_name,
                    sort_order=child_sort,
                    is_active=True,
                    parent_id=parent.pk,
                )


def flatten_category_tree(apps, schema_editor):
    MaterialCategory = apps.get_model('kho_npl', 'MaterialCategory')
    MaterialCategory.objects.filter(parent__isnull=False).update(parent=None)
    parent_codes = [row[0] for row in DEFAULT_MATERIAL_CATEGORY_TREE]
    MaterialCategory.objects.filter(code__in=parent_codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0009_material_specification'),
    ]

    operations = [
        migrations.AddField(
            model_name='materialcategory',
            name='parent',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='children',
                to='kho_npl.materialcategory',
                verbose_name='Nhóm cha',
            ),
        ),
        migrations.RunPython(build_category_tree, flatten_category_tree),
    ]
