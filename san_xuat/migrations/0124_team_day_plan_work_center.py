from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0123_team_stage_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxorderteamdayplan',
            name='work_center',
            field=models.ForeignKey(
                blank=True,
                help_text='Một bộ phận (slug) có thể tách SL cho nhiều tổ làm cùng lúc.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='order_team_day_plans',
                to='san_xuat.sxworkcenter',
                verbose_name='Tổ năng lực SX',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='sxorderteamdayplan',
            name='sx_order_team_day_plan_uniq',
        ),
        migrations.AddConstraint(
            model_name='sxorderteamdayplan',
            constraint=models.UniqueConstraint(
                condition=models.Q(work_center__isnull=False),
                fields=('sales_order', 'team_slug', 'plan_date', 'work_center'),
                name='sx_order_team_day_plan_wc_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='sxorderteamdayplan',
            constraint=models.UniqueConstraint(
                condition=models.Q(work_center__isnull=True),
                fields=('sales_order', 'team_slug', 'plan_date'),
                name='sx_order_team_day_plan_null_wc_uniq',
            ),
        ),
    ]
