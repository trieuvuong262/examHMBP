from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0007_product_bar_code_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[('', '—'), ('NAM', 'Nam'), ('NU', 'Nữ')],
                default='',
                help_text='Thuộc tính riêng của SKU, tách khỏi size (trước đây viết lồng "XL-NỮ").',
                max_length=10,
                verbose_name='Giới tính',
            ),
        ),
    ]
