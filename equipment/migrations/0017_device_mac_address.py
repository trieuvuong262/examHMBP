# Generated manually

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0016_remove_agent_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='mac_address',
            field=models.CharField(blank=True, db_index=True, max_length=17, verbose_name='MAC'),
        ),
        migrations.AddConstraint(
            model_name='device',
            constraint=models.UniqueConstraint(
                condition=~Q(mac_address=''),
                fields=('mac_address',),
                name='equipment_device_mac_unique',
            ),
        ),
    ]
