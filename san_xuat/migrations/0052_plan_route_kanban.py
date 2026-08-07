from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0051_plan_priority_five_levels'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxSalesOrderPlanStep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sequence', models.PositiveSmallIntegerField(default=10, verbose_name='Thứ tự')),
                ('process_name', models.CharField(max_length=120, verbose_name='Công đoạn')),
                ('planned_date', models.DateField(blank=True, db_index=True, null=True, verbose_name='Ngày kế hoạch')),
                ('minutes_per_unit', models.DecimalField(
                    decimal_places=4, default=Decimal('0'), max_digits=12, verbose_name='Phút / cái',
                )),
                ('sales_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='plan_steps',
                    to='san_xuat.sxsalesorder',
                    verbose_name='Đơn đặt hàng',
                )),
                ('work_center', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sales_order_plan_steps',
                    to='san_xuat.sxworkcenter',
                    verbose_name='Tổ / bộ phận',
                )),
            ],
            options={
                'verbose_name': 'Công đoạn kế hoạch đơn',
                'verbose_name_plural': 'Công đoạn kế hoạch đơn',
                'ordering': ['sequence', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='sxsalesorderplanstep',
            constraint=models.UniqueConstraint(
                fields=('sales_order', 'sequence'),
                name='sx_so_plan_step_seq_uniq',
            ),
        ),
        migrations.AddField(
            model_name='sxmoprocessstep',
            name='planned_date',
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name='Ngày kế hoạch'),
        ),
        migrations.AddField(
            model_name='sxmoprocessstep',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Chờ'),
                    ('in_progress', 'Đang làm'),
                    ('done', 'Xong'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
                verbose_name='TT công đoạn',
            ),
        ),
    ]
