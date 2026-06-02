from django.db import migrations, models


def backfill_repair_scope(apps, schema_editor):
    ServiceRequest = apps.get_model('service_requests', 'ServiceRequest')
    RequestType = apps.get_model('service_requests', 'RequestType')
    it_code = 'it_repair'
    try:
        it_type_id = RequestType.objects.filter(code=it_code).values_list('pk', flat=True).first()
    except Exception:
        it_type_id = None
    if not it_type_id:
        return

    qs = ServiceRequest.objects.filter(request_type_id=it_type_id, repair_equipment_scope='')
    Device = apps.get_model('equipment', 'Device')

    for req in qs.iterator():
        scope = 'it'
        if req.equipment_id:
            device = Device.objects.filter(pk=req.equipment_id).first()
            if device:
                try:
                    from equipment.services.device_categories import import_profile_for_code

                    if import_profile_for_code(getattr(device, 'category', '')) == 'machine':
                        scope = 'production'
                except Exception:
                    pass
        ServiceRequest.objects.filter(pk=req.pk).update(repair_equipment_scope=scope)


class Migration(migrations.Migration):

    dependencies = [
        ('service_requests', '0006_rename_request_type_labels'),
        ('equipment', '0009_device_managed_department'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicerequest',
            name='repair_equipment_scope',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=20,
                verbose_name='Phạm vi thiết bị (hỗ trợ kỹ thuật)',
            ),
        ),
        migrations.RunPython(backfill_repair_scope, migrations.RunPython.noop),
    ]
