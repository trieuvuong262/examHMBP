from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0015_remove_device_remote_access_fields'),
    ]

    operations = [
        migrations.DeleteModel(name='UserAgentRegistration'),
        migrations.DeleteModel(name='AgentInstallToken'),
        migrations.DeleteModel(name='EquipmentScanControl'),
    ]
