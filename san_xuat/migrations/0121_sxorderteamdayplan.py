from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0120_sxworkcenter_is_subcontract'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxOrderTeamDayPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team_slug', models.CharField(db_index=True, max_length=40, verbose_name='Slug tổ')),
                ('plan_date', models.DateField(db_index=True, verbose_name='Ngày kế hoạch')),
                ('qty', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='Số lượng')),
                ('sales_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='team_day_plans',
                    to='san_xuat.sxsalesorder',
                    verbose_name='Đơn đặt hàng',
                )),
            ],
            options={
                'verbose_name': 'Phân bổ ngày tổ trên đơn',
                'verbose_name_plural': 'Phân bổ ngày tổ trên đơn',
                'ordering': ['plan_date', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='sxorderteamdayplan',
            constraint=models.UniqueConstraint(
                fields=('sales_order', 'team_slug', 'plan_date'),
                name='sx_order_team_day_plan_uniq',
            ),
        ),
        migrations.AddIndex(
            model_name='sxorderteamdayplan',
            index=models.Index(fields=['sales_order', 'team_slug'], name='sx_order_team_day_so_slug'),
        ),
    ]
