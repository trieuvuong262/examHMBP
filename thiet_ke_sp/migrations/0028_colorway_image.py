from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0027_test_mode_design_help'),
    ]

    operations = [
        migrations.AlterField(
            model_name='colorway',
            name='color_codes',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Mã màu'),
        ),
    ]
