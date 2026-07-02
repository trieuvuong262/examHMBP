from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0016_production_shift_unique'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productionshiftproduct',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Bắt đầu công đoạn'),
        ),
        migrations.AlterField(
            model_name='productionshiftproduct',
            name='ended_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Kết thúc công đoạn'),
        ),
        migrations.AddField(
            model_name='productionshiftproduct',
            name='total_quantity',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Tổng sản lượng phiên'),
        ),
        migrations.AddField(
            model_name='productionshiftproduct',
            name='total_damaged_quantity',
            field=models.PositiveIntegerField(default=0, verbose_name='Tổng hư hỏng phiên'),
        ),
        migrations.AddField(
            model_name='productionshiftproduct',
            name='completion_note',
            field=models.CharField(blank=True, default='', max_length=500, verbose_name='Ghi chú phiên'),
        ),
    ]
