from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0140_qc_flow_size_defect'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorderroutingline',
            name='board_slug',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ghim khi đổi tổ năng lực. Trống = tính theo công đoạn như mặc định.',
                max_length=40,
                verbose_name='Slug bộ phận trên bảng',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorderplanstep',
            name='board_slug',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ghim khi đổi tổ năng lực để cột Bộ phận không đổi slug.',
                max_length=40,
                verbose_name='Slug bộ phận trên bảng',
            ),
        ),
        migrations.AddField(
            model_name='sxsalesorderplanstep',
            name='dept_label',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Chữ cột Bộ phận trước lần đổi tổ. Trống = đang hiện theo mặc định.',
                max_length=120,
                verbose_name='Tên bộ phận trên bảng',
            ),
        ),
    ]
