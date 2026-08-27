# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0097_qc_inspection_team_tabs'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxqccriteria',
            name='team_slug',
            field=models.CharField(
                blank=True,
                choices=[
                    ('cat', 'Cắt'),
                    ('inep', 'In - Ép'),
                    ('theu', 'Thêu'),
                    ('may', 'May'),
                    ('ht', 'Ủi - Gấp xếp'),
                    ('gh', 'Giao hàng thành phẩm'),
                ],
                db_index=True,
                default='',
                help_text='Tiêu chuẩn này hiện trên tab phiếu kiểm tra của tổ tương ứng.',
                max_length=20,
                verbose_name='Tổ',
            ),
        ),
    ]
