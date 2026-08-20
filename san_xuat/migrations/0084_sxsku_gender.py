from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0083_sxsize_scale'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsku',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[('', '—'), ('NAM', 'Nam'), ('NU', 'Nữ')],
                default='',
                help_text='Bản nam và bản nữ cùng style–màu–size là hai SKU khác nhau.',
                max_length=10,
                verbose_name='Giới tính',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='sxsku',
            name='sx_sku_style_color_size_uniq',
        ),
        migrations.AddConstraint(
            model_name='sxsku',
            constraint=models.UniqueConstraint(
                fields=('style_code', 'color_code', 'size_label', 'gender'),
                name='sx_sku_style_color_size_gender_uniq',
            ),
        ),
    ]
