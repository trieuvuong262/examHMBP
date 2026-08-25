from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0090_inter_step_hop_by_team'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorder',
            name='plan_start_date',
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text='Neo lịch trên lộ trình (kéo thả). Trống = dùng ngày dự kiến thực hiện.',
                null=True,
                verbose_name='Ngày bắt đầu KHSX',
            ),
        ),
    ]
