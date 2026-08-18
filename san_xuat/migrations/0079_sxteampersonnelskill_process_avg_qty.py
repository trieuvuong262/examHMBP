from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0078_smv_basis_seconds_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxteampersonnelskill',
            name='process_avg_qty',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Map key công đoạn → sản lượng trung bình (SP) phục vụ lương sản lượng.',
                verbose_name='Sản lượng TB theo công đoạn',
            ),
        ),
    ]
