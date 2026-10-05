# Generated manually — seed loại yêu cầu chung cho các đề xuất phi mua-hàng.

from django.db import migrations


def seed_general_proposal_type(apps, schema_editor):
    RequestType = apps.get_model('service_requests', 'RequestType')
    RequestType.objects.get_or_create(
        code='general_proposal',
        defaults={
            'name': 'Đề xuất chung',
            'description': (
                'Thanh toán/tạm ứng, tuyển dụng/điều chuyển, sửa chữa, cấp phát — '
                'duyệt theo cấp quản lý.'
            ),
            'is_active': True,
            'sort_order': 3,
        },
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('service_requests', '0009_servicerequest_extra_data_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_general_proposal_type, noop),
    ]
