from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0028_colorway_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='productdevelopment',
            name='reopen_edit_step',
            field=models.CharField(
                blank=True,
                default='',
                help_text='design | technical | sample — chỉ mở sửa công đoạn này khi đang chỉnh sau hoàn thành.',
                max_length=20,
                verbose_name='Công đoạn sửa sau huỷ hoàn thành',
            ),
        ),
    ]
