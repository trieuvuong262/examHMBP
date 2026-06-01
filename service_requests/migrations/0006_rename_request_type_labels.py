from django.db import migrations


def rename_request_type_labels(apps, schema_editor):
    RequestType = apps.get_model('service_requests', 'RequestType')
    RequestType.objects.filter(code='it_repair').update(
        name='Hỗ trợ kỹ thuật',
        description='Yêu cầu sửa chữa thiết bị — IT xử lý trực tiếp, không duyệt TL/BP.',
    )
    RequestType.objects.filter(code='asset_purchase').update(
        name='Đề xuất mua hàng',
    )


def revert_request_type_labels(apps, schema_editor):
    RequestType = apps.get_model('service_requests', 'RequestType')
    RequestType.objects.filter(code='it_repair').update(
        name='Sửa chữa IT',
        description='Báo hỏng máy tính, mạng, phần mềm — IT xử lý trực tiếp, không duyệt TL/BP.',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('service_requests', '0005_servicerequest_equipment'),
    ]

    operations = [
        migrations.RunPython(rename_request_type_labels, revert_request_type_labels),
    ]
