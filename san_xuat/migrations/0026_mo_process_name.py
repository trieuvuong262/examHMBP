from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0025_design_file_nas_storage'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxproductionorder',
            name='process_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Công đoạn chính trên lệnh (lấy từ BOM khi có).',
                max_length=120,
                verbose_name='Công đoạn',
            ),
        ),
    ]
