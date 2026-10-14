from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('thiet_ke_sp', '0013_dossier_product_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='productdevelopment',
            name='followers',
            field=models.ManyToManyField(
                blank=True,
                related_name='tksp_following',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Người theo dõi',
            ),
        ),
        migrations.AddField(
            model_name='comment',
            name='step',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Cả hồ sơ'),
                    ('proposal', 'Đề xuất'),
                    ('brief', 'Duyệt đề bài'),
                    ('design', 'Thiết kế'),
                    ('design_approval', 'Duyệt thiết kế'),
                    ('sample', 'Làm mẫu'),
                    ('evaluation', 'Đánh giá mẫu'),
                    ('master', 'Duyệt mẫu chuẩn'),
                    ('handover', 'Bàn giao SX'),
                ],
                default='',
                max_length=30,
                verbose_name='Bước',
            ),
        ),
    ]
