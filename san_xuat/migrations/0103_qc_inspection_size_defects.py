# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0102_sxsubcontractorder_sales_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxqcinspection',
            name='size_qtys',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='[{size, qty_pass, qty_fail}] khi phiếu không tách tổ.',
                verbose_name='SL theo size',
            ),
        ),
        migrations.AddField(
            model_name='sxqcinspectionteamresult',
            name='size_qtys',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='[{size, qty_pass, qty_fail}]',
                verbose_name='SL theo size',
            ),
        ),
        migrations.AddField(
            model_name='sxqcinspectiondefectline',
            name='team_slug',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                max_length=20,
                verbose_name='Tổ',
            ),
        ),
        migrations.AddField(
            model_name='sxqcinspectiondefectline',
            name='size_label',
            field=models.CharField(
                blank=True,
                default='',
                max_length=40,
                verbose_name='Size',
            ),
        ),
    ]
