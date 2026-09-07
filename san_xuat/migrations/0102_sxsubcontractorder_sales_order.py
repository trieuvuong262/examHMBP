# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def _backfill_sales_order(apps, schema_editor):
    SxSubcontractOrder = apps.get_model('san_xuat', 'SxSubcontractOrder')
    for row in (
        SxSubcontractOrder.objects.filter(sales_order_id__isnull=True, production_order_id__isnull=False)
        .iterator()
    ):
        so_id = getattr(row.production_order, 'sales_order_id', None)
        if so_id:
            row.sales_order_id = so_id
            row.save(update_fields=['sales_order_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0101_alter_sxqcrequest_stage_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsubcontractorder',
            name='sales_order',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='subcontract_orders',
                to='san_xuat.sxsalesorder',
                verbose_name='Đơn đặt hàng',
            ),
        ),
        migrations.RunPython(_backfill_sales_order, migrations.RunPython.noop),
    ]
