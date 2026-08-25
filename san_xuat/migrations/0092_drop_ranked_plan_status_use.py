from django.db import migrations, models


def ranked_to_queued(apps, schema_editor):
    SxSalesOrder = apps.get_model('san_xuat', 'SxSalesOrder')
    SxSalesOrder.objects.filter(plan_status='ranked').update(plan_status='queued')


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0091_sales_order_plan_start_date'),
    ]

    operations = [
        migrations.RunPython(ranked_to_queued, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='sxsalesorder',
            name='plan_status',
            field=models.CharField(
                choices=[
                    ('queued', 'Chờ xếp'),
                    ('ranked', 'Chờ xếp'),
                    ('released', 'Đã chuyển SX'),
                    ('in_progress', 'Đang sản xuất'),
                    ('done', 'Hoàn thành'),
                    ('on_hold', 'Tạm giữ'),
                ],
                db_index=True,
                default='queued',
                max_length=20,
                verbose_name='TT kế hoạch SX',
            ),
        ),
    ]
