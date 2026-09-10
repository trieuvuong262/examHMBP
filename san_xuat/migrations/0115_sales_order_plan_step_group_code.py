from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0114_sales_order_plan_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorderplanstep',
            name='group_code',
            field=models.CharField(
                blank=True,
                default='',
                max_length=30,
                verbose_name='Mã nhóm',
            ),
        ),
    ]
