from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0002_maintenancelog_service_request'),
    ]

    operations = [
        migrations.CreateModel(
            name='EquipmentScanControl',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agent_rescan_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Điều khiển quét Agent',
            },
        ),
    ]
