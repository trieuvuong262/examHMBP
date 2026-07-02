from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0017_production_session_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productionshiftproduct',
            name='total_quantity',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='Tổng sản lượng phiên',
            ),
        ),
        migrations.AlterField(
            model_name='productionhourlyquantity',
            name='quantity',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                verbose_name='Sản lượng giờ',
            ),
        ),
    ]
