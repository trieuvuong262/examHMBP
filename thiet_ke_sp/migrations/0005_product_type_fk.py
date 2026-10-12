import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0003_catalog_type_style_kv_map'),
        ('thiet_ke_sp', '0004_product_group_type_from_catalog'),
    ]

    operations = [
        migrations.RemoveField(model_name='productdevelopment', name='product_type'),
        migrations.RenameField(model_name='productdevelopment', old_name='catalog_type', new_name='product_type'),
        migrations.AlterField(
            model_name='productdevelopment',
            name='product_type',
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='tksp_dossiers', to='kho_san_pham.producttype', verbose_name='Loại sản phẩm',
            ),
        ),
    ]
