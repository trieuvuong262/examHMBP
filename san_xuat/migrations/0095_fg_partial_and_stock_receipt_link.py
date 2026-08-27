# Generated manually

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_san_pham', '0014_stock_receipt'),
        ('san_xuat', '0094_sxfgreceiptline_warehouse'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sxfgreceiptrequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Nháp'),
                    ('submitted', 'Đã gửi'),
                    ('partial', 'Còn hàng chưa nhập'),
                    ('done', 'Hoàn thành'),
                    ('cancelled', 'Hủy'),
                ],
                db_index=True,
                default='draft',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='sxfgreceiptline',
            name='stock_receipt',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='fg_lines',
                to='kho_san_pham.stockreceipt',
                verbose_name='Phiếu nhập kho SP',
            ),
        ),
    ]
