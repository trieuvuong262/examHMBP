"""Đồng bộ tên bộ phận của nhóm xuống thư viện, routing và đơn hàng."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from san_xuat.hub_models import SxSalesOrderRoutingLine
from san_xuat.ie_models import SxOperation, SxOperationGroup, SxRoutingLine
from san_xuat.services.capacity_from_hrm import resolve_work_center_code


# Chuyển dữ liệu khâu SX cũ sang các bộ phận hiện hành.
GROUP_PREFIX_DEPARTMENTS = (
    ('PRE_', 'Cắt'),
    ('SUB_', 'In - Ép'),
    ('CHK_', 'May'),
    ('HTF_', 'In - Ép'),
    ('SEW_', 'May'),
    ('IRN_', 'Ủi - Gấp xếp'),
    ('FOD_', 'Giao hàng thành phẩm'),
)

# Các công đoạn từng được nhập nhầm vào PRE_PRE dù thuộc nhóm In - Ép.
OPERATION_GROUP_OVERRIDES = {
    'PRE_PRE_1005': 'HTF_LOG',
    'PRE_PRE_1007': 'HTF_HEM',
}


def _department_for_group(group: SxOperationGroup):
    code = (group.code or '').strip().upper()
    for prefix, department_name in GROUP_PREFIX_DEPARTMENTS:
        if code.startswith(prefix):
            return resolve_work_center_code(department_name)

    current_default = (
        (group.default_work_center_code or '').strip()
        or (
            (group.default_work_center.code or '').strip()
            if group.default_work_center_id
            else ''
        )
    )
    if current_default:
        hit = resolve_work_center_code(current_default)
        if hit:
            return hit
    return resolve_work_center_code((group.process_stage_label or '').strip())


class Command(BaseCommand):
    help = (
        'Đổi khâu SX cũ thành tên bộ phận và đồng bộ bộ phận xuống '
        'thư viện công đoạn, routing, snapshot đơn hàng.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Chạy thử, không lưu.')

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        stats = {
            'groups': 0,
            'operations': 0,
            'routing_lines': 0,
            'order_lines': 0,
        }
        unresolved: list[str] = []

        with transaction.atomic():
            groups = list(
                SxOperationGroup.objects.select_related('default_work_center').order_by('code')
            )
            group_departments = {}
            for group in groups:
                department = _department_for_group(group)
                if department is None:
                    unresolved.append(group.code)
                    continue
                group_departments[group.pk] = department
                department_name = (department.name or department.team_label or department.code).strip()
                if (
                    group.process_stage_label != department_name
                    or group.process_stage_id is not None
                    or group.default_work_center_id is not None
                    or group.default_work_center_code
                ):
                    group.process_stage_label = department_name[:100]
                    group.process_stage = None
                    group.default_work_center = None
                    group.default_work_center_code = ''
                    group.save(update_fields=[
                        'process_stage_label',
                        'process_stage',
                        'default_work_center',
                        'default_work_center_code',
                        'updated_at',
                    ])
                    stats['groups'] += 1

            groups_by_code = {
                (group.code or '').strip().casefold(): group
                for group in groups
            }

            for operation in SxOperation.objects.select_related('group').iterator():
                target_group_code = OPERATION_GROUP_OVERRIDES.get(
                    (operation.op_code or '').strip().upper()
                )
                target_group = (
                    groups_by_code.get(target_group_code.casefold())
                    if target_group_code
                    else None
                )
                changed_fields = []
                if target_group is not None and operation.group_id != target_group.pk:
                    operation.group = target_group
                    changed_fields.append('group')
                department = group_departments.get(operation.group_id)
                if department is None:
                    continue
                department_name = (
                    department.name or department.team_label or department.code
                ).strip()[:100]
                if operation.process_stage_label != department_name:
                    operation.process_stage_label = department_name
                    changed_fields.append('process_stage_label')
                if changed_fields:
                    operation.save(update_fields=[*changed_fields, 'updated_at'])
                    stats['operations'] += 1

            for line in SxRoutingLine.objects.select_related(
                'operation__group', 'work_center',
            ).iterator():
                group = (
                    line.operation.group
                    if line.operation_id and line.operation.group_id
                    else groups_by_code.get((line.group_code or '').strip().casefold())
                )
                department = group_departments.get(group.pk) if group else None
                if department is None:
                    continue
                target_group_code = (group.code or '').strip()
                if (
                    line.work_center_id != department.pk
                    or line.work_center_code != department.code
                    or line.group_code != target_group_code
                ):
                    line.work_center = department
                    line.work_center_code = department.code
                    line.group_code = target_group_code
                    line.save(update_fields=['work_center', 'work_center_code', 'group_code'])
                    stats['routing_lines'] += 1

            for line in SxSalesOrderRoutingLine.objects.select_related(
                'operation__group', 'work_center',
            ).iterator():
                group = (
                    line.operation.group
                    if line.operation_id and line.operation.group_id
                    else groups_by_code.get((line.group_code or '').strip().casefold())
                )
                department = group_departments.get(group.pk) if group else None
                if department is None:
                    continue
                target_group_code = (group.code or '').strip()
                if (
                    line.work_center_id != department.pk
                    or line.work_center_code != department.code
                    or line.group_code != target_group_code
                ):
                    line.work_center = department
                    line.work_center_code = department.code
                    line.group_code = target_group_code
                    line.save(update_fields=['work_center', 'work_center_code', 'group_code'])
                    stats['order_lines'] += 1

            if dry_run:
                transaction.set_rollback(True)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN (không lưu)'))
        self.stdout.write(
            'Đồng bộ: '
            f'nhóm={stats["groups"]}, '
            f'công đoạn={stats["operations"]}, '
            f'routing={stats["routing_lines"]}, '
            f'dòng đơn={stats["order_lines"]}'
        )
        if unresolved:
            self.stdout.write(self.style.WARNING(
                'Chưa xác định bộ phận: ' + ', '.join(unresolved)
            ))
        else:
            self.stdout.write(self.style.SUCCESS('Tất cả nhóm đã có tên bộ phận.'))
