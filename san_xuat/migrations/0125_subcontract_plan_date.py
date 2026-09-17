from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0124_team_day_plan_work_center'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsubcontractorder',
            name='plan_date',
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text='Gắn phiếu GC với một phần tách (ngày / SL) trên KHSX. Trống = cả công đoạn.',
                null=True,
                verbose_name='Ngày KHSX thuê GC',
            ),
        ),
        migrations.AddField(
            model_name='sxsubcontractorder',
            name='work_center',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='subcontract_orders',
                to='san_xuat.sxworkcenter',
                verbose_name='Tổ KHSX thuê GC',
            ),
        ),
    ]
