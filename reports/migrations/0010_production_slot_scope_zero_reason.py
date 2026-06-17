from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0009_production_product_optional'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionshiftproduct',
            name='first_slot_index',
            field=models.PositiveSmallIntegerField(
                default=0,
                verbose_name='Khung giờ bắt đầu phiên mã hàng',
            ),
        ),
        migrations.AddField(
            model_name='productionhourlyquantity',
            name='zero_reason',
            field=models.CharField(
                blank=True,
                default='',
                max_length=200,
                verbose_name='Lý do sản lượng 0',
            ),
        ),
    ]
