from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0026_tech_spec_label'),
    ]

    operations = [
        migrations.AlterField(
            model_name='modulesetting',
            name='test_mode',
            field=models.BooleanField(
                default=True,
                help_text='Bật: chuyển kỹ thuật không bắt ảnh 2 mặt, colorway và file thiết kế gốc; duyệt thiết kế bỏ bớt điều kiện; hồ sơ đã duyệt vẫn sửa được. Tắt: về quy tắc chính thức.',
                verbose_name='Trạng thái test',
            ),
        ),
    ]
