import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0017_design_transfer'),
        ('thiet_ke_sp', '0012_drop_handover_receivers'),
    ]

    operations = [
        migrations.AddField(
            model_name='productdevelopment',
            name='product_type',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='tksp_dossiers',
                to='kho_san_pham.producttype',
                verbose_name='Loại mã (Style trong Thư viện)',
            ),
        ),
    ]
