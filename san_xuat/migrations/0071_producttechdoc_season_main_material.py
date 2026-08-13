from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0070_bomversion_overhead_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='producttechdoc',
            name='season',
            field=models.CharField(
                blank=True,
                default='',
                max_length=80,
                verbose_name='Mùa / BST',
            ),
        ),
        migrations.AddField(
            model_name='producttechdoc',
            name='main_material',
            field=models.CharField(
                blank=True,
                default='',
                max_length=120,
                verbose_name='Chất liệu chính',
            ),
        ),
    ]
