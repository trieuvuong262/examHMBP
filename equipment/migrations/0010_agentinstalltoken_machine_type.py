from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0009_device_managed_department'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentinstalltoken',
            name='machine_type',
            field=models.CharField(
                choices=[('company', 'Máy công ty'), ('personal', 'Máy cá nhân')],
                default='company',
                max_length=20,
                verbose_name='Loại máy',
            ),
        ),
    ]
