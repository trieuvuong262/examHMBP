from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0068_alter_sxoperation_base_smv_min_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='techdocdesignfile',
            name='purpose',
            field=models.CharField(
                choices=[('design', 'Rập / tài liệu'), ('gallery', 'Ảnh mô tả')],
                db_index=True,
                default='design',
                max_length=20,
                verbose_name='Loại',
            ),
        ),
        migrations.AddField(
            model_name='techdocdesignfile',
            name='sort_order',
            field=models.PositiveIntegerField(default=0, verbose_name='Thứ tự'),
        ),
    ]
