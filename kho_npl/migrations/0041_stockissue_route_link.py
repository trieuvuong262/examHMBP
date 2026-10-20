from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0144_fill_closed_team_output'),
        ('kho_npl', '0040_supplier_order_contact'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockissue',
            name='sales_order',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='npl_stock_issues',
                to='san_xuat.sxsalesorder',
                verbose_name='Đơn hàng',
            ),
        ),
        migrations.AddField(
            model_name='stockissue',
            name='work_center',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='npl_stock_issues',
                to='san_xuat.sxworkcenter',
                verbose_name='Tổ trên lộ trình',
            ),
        ),
    ]
