from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0150_bomline_material_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsubcontractorder',
            name='unit_price',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Chốt trên phiếu; phí GC = đơn giá × SL nhận.',
                max_digits=14,
                verbose_name='Đơn giá GC / SP (VNĐ)',
            ),
        ),
        migrations.AddField(
            model_name='sxsubcontractorder',
            name='progress_date',
            field=models.DateField(
                blank=True,
                help_text='Ngày SL nhận GC được ghi vào tiến độ tổ.',
                null=True,
                verbose_name='Ngày ghi tiến độ GC',
            ),
        ),
        migrations.AddField(
            model_name='sxsubcontractorder',
            name='progress_posted',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='{size: SL} — để huỷ nhận trừ đúng phần đã cộng.',
                verbose_name='SL GC đã ghi tiến độ',
            ),
        ),
        migrations.AlterField(
            model_name='sxteamprogresslog',
            name='kind',
            field=models.CharField(
                choices=[('edit', 'Nhập tay'), ('complete', 'Hoàn thành'), ('gc', 'Nhận GC')],
                default='edit',
                max_length=10,
                verbose_name='Loại',
            ),
        ),
    ]
