from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0044_material_groups'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='size',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Size'),
        ),
    ]
