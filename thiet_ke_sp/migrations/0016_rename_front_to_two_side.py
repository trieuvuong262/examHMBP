from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0015_alter_task_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attachment',
            name='kind',
            field=models.CharField(
                choices=[
                    ('reference', 'Tham khảo'),
                    ('front', 'Ảnh 2 mặt'),
                    ('back', 'Ảnh mặt sau'),
                    ('detail', 'Ảnh chi tiết'),
                    ('design_source', 'File thiết kế gốc'),
                    ('design_preview', 'File xem nhanh'),
                    ('colorway', 'Ảnh colorway'),
                    ('tech_spec', 'Bảng thông số / tài liệu kỹ thuật'),
                    ('sample_photo', 'Ảnh mẫu thực tế'),
                    ('evaluation', 'Biên bản đánh giá'),
                    ('cost', 'Bảng giá thành'),
                    ('product_photo', 'Ảnh sản phẩm'),
                    ('other', 'Khác'),
                ],
                default='other',
                max_length=20,
            ),
        ),
    ]
