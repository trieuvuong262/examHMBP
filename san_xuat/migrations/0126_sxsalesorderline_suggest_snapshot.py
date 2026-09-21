from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0125_subcontract_plan_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorderline',
            name='suggest_snapshot',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    'Bảng công cụ đề xuất lúc Áp dụng: '
                    '{coef, round, days, sizes, stock, velocity, raw, suggested, confirm, ratio, …}.'
                ),
                verbose_name='Snapshot đề xuất SL',
            ),
        ),
    ]
