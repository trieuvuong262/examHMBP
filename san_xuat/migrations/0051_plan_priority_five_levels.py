from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0050_sales_order_plan_board'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sxsalesorder',
            name='plan_priority',
            field=models.CharField(
                choices=[
                    ('critical', 'Rất gấp'),
                    ('urgent', 'Gấp'),
                    ('high', 'Cao'),
                    ('normal', 'Thường'),
                    ('low', 'Thấp'),
                ],
                db_index=True,
                default='normal',
                max_length=12,
                verbose_name='Mức độ gấp',
            ),
        ),
    ]
