from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0004_rename_productstyle_indexes'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='product',
            name='kho_sp_product_accounting_code_uniq',
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['accounting_code'],
                name='kho_sp_prod_account_0a1b2c_idx',
            ),
        ),
    ]
