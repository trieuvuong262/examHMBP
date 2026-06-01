import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0001_initial'),
        ('service_requests', '0005_servicerequest_equipment'),
    ]

    operations = [
        migrations.AddField(
            model_name='maintenancelog',
            name='service_request',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='equipment_logs',
                to='service_requests.servicerequest',
                verbose_name='Yêu cầu hỗ trợ',
            ),
        ),
    ]
