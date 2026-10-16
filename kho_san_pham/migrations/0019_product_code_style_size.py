from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0018_product_image_nas'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='code',
            field=models.CharField(
                db_index=True,
                help_text='SKU từ thiết kế = Style-Size (vd. JP-TEE-00-SP8516975-L). Màu là thuộc tính của mã gốc.',
                max_length=100,
                verbose_name='SKU',
            ),
        ),
    ]
