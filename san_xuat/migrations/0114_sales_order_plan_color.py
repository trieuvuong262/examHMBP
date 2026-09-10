from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0113_order_npl_qty_allocated'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorder',
            name='plan_color',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Màu tự chọn trên lộ trình (#RRGGBB). Trống = màu hệ thống.',
                max_length=7,
                verbose_name='Màu lộ trình',
            ),
        ),
    ]
