"""Đổi mã bước thực hiện cuối của đề xuất chung sang `general_execution`.

Trước đây bước cuối dùng `it_repair_execution` (sửa chữa) hoặc `procurement_purchase`
(các loại khác) nên không ai xử lý được / hiện sai form. Chỉ áp dụng cho phiếu
`general_proposal`; phiếu mua hàng và hỗ trợ kỹ thuật giữ nguyên.
"""

from django.db import migrations

OLD_CODES = ('it_repair_execution', 'procurement_purchase')
NEW_CODE = 'general_execution'


def forwards(apps, schema_editor):
    Step = apps.get_model('service_requests', 'ServiceRequestStep')
    Step.objects.filter(
        request__request_type__code='general_proposal',
        step_code__in=OLD_CODES,
    ).update(step_code=NEW_CODE)


def backwards(apps, schema_editor):
    Step = apps.get_model('service_requests', 'ServiceRequestStep')
    Step.objects.filter(
        request__request_type__code='general_proposal',
        step_code=NEW_CODE,
        request__request_subtype='repair',
    ).update(step_code='it_repair_execution')
    Step.objects.filter(
        request__request_type__code='general_proposal',
        step_code=NEW_CODE,
    ).update(step_code='procurement_purchase')


class Migration(migrations.Migration):

    dependencies = [
        ('service_requests', '0010_seed_general_proposal_type'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
