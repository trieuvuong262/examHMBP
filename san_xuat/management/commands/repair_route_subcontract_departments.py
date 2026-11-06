"""Sửa nhãn bộ phận route board khi tổ thực hiện là tổ thuê ngoài."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from san_xuat.hub_models import SxSalesOrderPlanStep, SxSalesOrderRoutingLine
from san_xuat.services.inter_step_times import _group_slug_scope, _step_team_slug
from san_xuat.services.team_division_map import gc_work_center_items


class Command(BaseCommand):
    help = (
        'Sửa board_slug/dept_label của plan step có tổ thuê ngoài; '
        'mặc định chỉ dry-run, dùng --apply để ghi.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Ghi thay đổi và rebuild route sheet.')
        parser.add_argument('--order-code', default='', help='Chỉ xử lý một mã đơn cụ thể.')

    def handle(self, *args, **options):
        apply = bool(options['apply'])
        code = (options.get('order_code') or '').strip()
        gc_work_center_ids = {
            int(item['work_center_id'])
            for item in gc_work_center_items()
            if item.get('work_center_id')
        }
        steps = SxSalesOrderPlanStep.objects.select_related(
            'sales_order', 'work_center',
        ).filter(
            work_center_id__in=gc_work_center_ids,
            sales_order__is_demo=False,
        )
        if code:
            steps = steps.filter(sales_order__code=code)

        changes: list[tuple[object, str, str]] = []
        skipped = 0
        with _group_slug_scope():
            for step in steps.order_by('sales_order_id', 'sequence', 'id').iterator():
                candidates = list(
                    SxSalesOrderRoutingLine.objects.select_related(
                        'sales_order_line', 'work_center', 'operation__group',
                    ).filter(
                        sales_order_line__order_id=step.sales_order_id,
                        group_code=step.group_code,
                        op_name_vi=step.process_name,
                        total_operation_smv__gt=0,
                    )
                )
                slugs = {_step_team_slug(line) for line in candidates}
                slugs.discard(None)
                slugs = {slug.strip().lower() for slug in slugs if slug and slug.strip()}
                if len(slugs) != 1:
                    skipped += 1
                    continue
                slug = next(iter(slugs))
                label = ''
                for line in candidates:
                    candidate = getattr(line.operation, 'group', None) if line.operation_id else None
                    if candidate is not None:
                        label = (candidate.process_stage_label or '').strip()
                    if label:
                        break
                if not label:
                    skipped += 1
                    continue
                if step.board_slug == slug and step.dept_label == label:
                    continue
                changes.append((step, slug, label))

        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(f'[{mode}] candidate changes: {len(changes)}, skipped/ambiguous: {skipped}')
        for step, slug, label in changes:
            self.stdout.write(
                f'  {step.sales_order.code} step={step.pk} '
                f'{step.board_slug or "-"}/{step.dept_label or "-"} -> {slug}/{label}'
            )
        if not apply or not changes:
            return

        affected: set[int] = set()
        with transaction.atomic():
            for step, slug, label in changes:
                SxSalesOrderPlanStep.objects.filter(pk=step.pk).update(
                    board_slug=slug[:40], dept_label=label[:120],
                )
                affected.add(int(step.sales_order_id))
        from san_xuat.services.route_sheet import refresh_route_sheets

        refresh_route_sheets(sorted(affected))
        self.stdout.write(self.style.SUCCESS(f'Applied {len(changes)} changes; refreshed {len(affected)} route sheets.'))
