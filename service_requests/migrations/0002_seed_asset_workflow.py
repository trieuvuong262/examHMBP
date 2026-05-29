from django.db import migrations


def seed_asset_purchase_workflow(apps, schema_editor):
    RequestType = apps.get_model('service_requests', 'RequestType')
    RequestTypeStepTemplate = apps.get_model('service_requests', 'RequestTypeStepTemplate')
    Department = apps.get_model('hrm', 'Department')

    request_type, _ = RequestType.objects.get_or_create(
        code='asset_purchase',
        defaults={
            'name': 'Đề xuất mua tài sản',
            'description': (
                'Quy trình: Trưởng bộ phận duyệt → Kế toán duyệt chi phí → Thu mua thực hiện.'
            ),
            'is_active': True,
            'sort_order': 1,
        },
    )

    accounting = Department.objects.filter(name__icontains='kế toán').first()
    if not accounting:
        accounting = Department.objects.filter(name__icontains='ke toan').first()
    procurement = Department.objects.filter(name__icontains='thu mua').first()
    if not procurement:
        procurement = Department.objects.filter(name__icontains='mua hàng').first()

    steps = [
        {
            'step_order': 1,
            'name': 'Trưởng bộ phận duyệt',
            'step_kind': 'approval',
            'assignee_rule': 'direct_manager',
            'target_department': None,
        },
        {
            'step_order': 2,
            'name': 'Kế toán duyệt chi phí',
            'step_kind': 'approval',
            'assignee_rule': 'department_queue',
            'target_department': accounting,
        },
        {
            'step_order': 3,
            'name': 'Thu mua thực hiện',
            'step_kind': 'execution',
            'assignee_rule': 'department_queue',
            'target_department': procurement,
        },
    ]

    for step in steps:
        RequestTypeStepTemplate.objects.update_or_create(
            request_type=request_type,
            step_order=step['step_order'],
            defaults={
                'name': step['name'],
                'step_kind': step['step_kind'],
                'assignee_rule': step['assignee_rule'],
                'target_department': step['target_department'],
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('service_requests', '0001_initial'),
        ('hrm', '0022_add_service_requests_module'),
    ]

    operations = [
        migrations.RunPython(seed_asset_purchase_workflow, noop),
    ]
