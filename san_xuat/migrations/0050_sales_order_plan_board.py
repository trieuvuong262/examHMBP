from django.db import migrations, models
from django.utils import timezone


def backfill_plan_queue(apps, schema_editor):
    SxSalesOrder = apps.get_model('san_xuat', 'SxSalesOrder')
    SxProductionOrder = apps.get_model('san_xuat', 'SxProductionOrder')
    now = timezone.now()
    for order in SxSalesOrder.objects.filter(confirm_status='confirmed', is_demo=False):
        has_mo = SxProductionOrder.objects.filter(
            sales_order_id=order.pk, is_demo=False,
        ).exclude(status='cancelled').exists()
        updates = {}
        if not order.plan_queued_at:
            updates['plan_queued_at'] = getattr(order, 'created_at', None) or now
        if has_mo:
            mos = list(
                SxProductionOrder.objects.filter(
                    sales_order_id=order.pk, is_demo=False,
                ).exclude(status='cancelled')
            )
            statuses = {m.status for m in mos}
            if statuses and statuses <= {'done'}:
                updates['plan_status'] = 'done'
            elif 'in_progress' in statuses:
                updates['plan_status'] = 'in_progress'
            else:
                updates['plan_status'] = 'released'
        else:
            updates.setdefault('plan_status', 'queued')
        if updates:
            for k, v in updates.items():
                setattr(order, k, v)
            order.save(update_fields=list(updates.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0049_sales_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorder',
            name='plan_hold_reason',
            field=models.CharField(blank=True, default='', max_length=500, verbose_name='Lý do tạm giữ'),
        ),
        migrations.AddField(
            model_name='sxsalesorder',
            name='plan_priority',
            field=models.CharField(
                choices=[('high', 'Cao'), ('normal', 'Thường'), ('low', 'Thấp')],
                db_index=True,
                default='normal',
                max_length=10,
                verbose_name='Ưu tiên SX',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorder',
            name='plan_queued_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Vào hàng đợi lúc'),
        ),
        migrations.AddField(
            model_name='sxsalesorder',
            name='plan_rank',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='Thứ tự xếp'),
        ),
        migrations.AddField(
            model_name='sxsalesorder',
            name='plan_score',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Điểm xếp hạng',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorder',
            name='plan_status',
            field=models.CharField(
                choices=[
                    ('queued', 'Chờ xếp'),
                    ('ranked', 'Đã xếp hạng'),
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
        migrations.RunPython(backfill_plan_queue, migrations.RunPython.noop),
    ]
