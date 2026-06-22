from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0014_device_rustdesk'),
        ('audit', '0009_rustdeskhost'),
    ]

    operations = [
        migrations.RemoveField(model_name='device', name='rustdesk_id'),
        migrations.RemoveField(model_name='device', name='rustdesk_password'),
        migrations.RemoveField(model_name='device', name='ultraviewer_id'),
        migrations.RemoveField(model_name='device', name='ultraviewer_password'),
    ]
