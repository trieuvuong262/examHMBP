from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0022_seed_final_approval'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobposting',
            name='position',
            field=models.CharField(max_length=100, verbose_name='Vị trí'),
        ),
    ]
