from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0148_sxmoprocessstep_applied_unit_smv'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxmoprocessstep',
            name='op_code',
            field=models.CharField(blank=True, db_index=True, default='', help_text='Khóa ghép với OB đơn hàng (trống thì ghép theo tên).', max_length=30, verbose_name='Mã công đoạn'),
        ),
        migrations.AddField(
            model_name='sxmoprocessstep',
            name='removed_from_ob',
            field=models.BooleanField(default=False, help_text='Công đoạn đã xóa khỏi OB đơn nhưng đã có sản lượng nên giữ lại.', verbose_name='Không còn trong OB'),
        ),
    ]
