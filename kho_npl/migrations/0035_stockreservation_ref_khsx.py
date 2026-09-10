from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0034_alter_material_base_price'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stockreservation',
            name='ref_type',
            field=models.CharField(
                choices=[
                    ('ycx', 'Yêu cầu xuất'),
                    ('khnvl', 'Kế hoạch nguyên phụ liệu'),
                    ('khsx', 'Đặt chỗ KHSX'),
                    ('mo', 'Lệnh sản xuất'),
                ],
                db_index=True,
                max_length=10,
            ),
        ),
    ]
