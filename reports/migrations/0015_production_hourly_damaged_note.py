from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0014_daily_attachment_link_tab'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionhourlyquantity',
            name='damaged_quantity',
            field=models.PositiveIntegerField(default=0, verbose_name='Số lượng hư hỏng'),
        ),
        migrations.AddField(
            model_name='productionhourlyquantity',
            name='note',
            field=models.CharField(blank=True, default='', max_length=500, verbose_name='Ghi chú'),
        ),
    ]
