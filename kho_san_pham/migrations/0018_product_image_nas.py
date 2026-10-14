from django.db import migrations, models

import kho_san_pham.models
import san_xuat.design_nas_storage


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0017_design_transfer'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='image',
            field=models.ImageField(
                blank=True,
                max_length=500,
                storage=san_xuat.design_nas_storage.DesignDocNasStorage(),
                upload_to=kho_san_pham.models.product_image_upload_to,
                verbose_name='Hình ảnh',
            ),
        ),
    ]
