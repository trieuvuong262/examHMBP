from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0073_alter_sxsalesorder_dates'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorderline',
            name='bom_line_overrides',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Snapshot NPL từ BOM khi lên đơn: [{bom_line_id, material_code, qty, scrap_pct, ...}].',
                verbose_name='NVL áp dụng trên đơn',
            ),
        ),
    ]
