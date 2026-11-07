"""Khôi phục bộ phận trên OB đơn hàng theo routing hồ sơ thiết kế."""

from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from san_xuat.hub_models import (
    SxOrderTeamDayPlan,
    SxSalesOrderPlanStep,
    SxSalesOrderRoutingLine,
)
from san_xuat.services.capacity_from_hrm import division_id_from_work_center_code
from san_xuat.services.inter_step_times import _group_slug_scope, _step_team_slug
from san_xuat.services.plan_board import _plan_step_team_slug


class Command(BaseCommand):
    help = (
        'Đưa work_center của SxSalesOrderRoutingLine về routing nguồn khi bị '
        'assign_plan_team ghi đè bằng tổ KHSX; mặc định chỉ dry-run, dùng --apply để ghi.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Ghi thay đổi.')
        parser.add_argument('--order-id', type=int, default=0, help='Chỉ xử lý một đơn (id).')
        parser.add_argument('--order-code', default='', help='Chỉ xử lý một mã đơn.')
        parser.add_argument(
            '--include-unmatched',
            action='store_true',
            help='Sửa cả dòng lệch mà tổ hiện tại không có trong kế hoạch tổ của đơn.',
        )

    def handle(self, *args, **options):
        apply = bool(options['apply'])
        include_unmatched = bool(options['include_unmatched'])
        lines = SxSalesOrderRoutingLine.objects.select_related(
            'sales_order_line__order', 'work_center', 'source_routing_line__work_center',
        ).filter(
            source_routing_line__isnull=False,
            source_routing_line__work_center__isnull=False,
            sales_order_line__order__is_demo=False,
        )
        if options['order_id']:
            lines = lines.filter(sales_order_line__order_id=options['order_id'])
        code = (options.get('order_code') or '').strip()
        if code:
            lines = lines.filter(sales_order_line__order__code=code)

        drifted = [
            ln for ln in lines.order_by('sales_order_line__order_id', 'seq_no', 'id')
            if ln.work_center_id != ln.source_routing_line.work_center_id
        ]
        order_ids = {ln.sales_order_line.order_id for ln in drifted}
        # assign_plan_team cũ ghi tổ KHSX của slug bộ phận vào mọi dòng OB cùng
        # slug; chỉ (slug, tổ) có trong plan step/day plan mới là dấu vết đó.
        assigned: dict[int, set[tuple[str, int]]] = defaultdict(set)
        fixes: list[SxSalesOrderRoutingLine] = []
        groups: dict[tuple, list[SxSalesOrderRoutingLine]] = defaultdict(list)
        with _group_slug_scope():
            for step in SxSalesOrderPlanStep.objects.select_related('work_center').filter(
                sales_order_id__in=order_ids, work_center_id__isnull=False,
            ):
                assigned[step.sales_order_id].add((_plan_step_team_slug(step), step.work_center_id))
            for oid, slug, wc_id in SxOrderTeamDayPlan.objects.filter(
                sales_order_id__in=order_ids, work_center_id__isnull=False,
            ).values_list('sales_order_id', 'team_slug', 'work_center_id'):
                assigned[oid].add(((slug or '').strip().lower(), wc_id))

            for ln in drifted:
                order = ln.sales_order_line.order
                src = ln.source_routing_line
                src_slug = (_step_team_slug(src) or '').strip().lower()
                dept_slug = (getattr(ln, 'board_slug', '') or '').strip().lower() or src_slug
                # Routing nguồn trỏ vào tổ (không phải bộ phận HRD-*) thì có thể
                # đã bị publish từ OB lỗi — không lấy làm chuẩn.
                matched = (
                    bool(dept_slug)
                    and dept_slug == src_slug
                    and division_id_from_work_center_code(src.work_center.code) is not None
                    and (dept_slug, ln.work_center_id) in assigned[order.pk]
                )
                groups[(order.pk, order.code, order.plan_status, matched, dept_slug,
                        _wc_label(ln.work_center), _wc_label(src.work_center))].append(ln)
                if matched or include_unmatched:
                    fixes.append(ln)

        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(
            f'[{mode}] dòng OB lệch routing nguồn: {len(drifted)} '
            f'({len(order_ids)} đơn); sẽ sửa: {len(fixes)}'
        )
        for (oid, ocode, status, matched, slug, cur, src), rows in groups.items():
            tag = 'FIX ' if (matched or include_unmatched) else 'SKIP'
            reason = 'tổ KHSX' if matched else 'không thấy trong KHSX'
            self.stdout.write(
                f'  {tag} order={oid} {ocode} [{status or "-"}] {slug or "-"}: {cur} -> {src} '
                f'x{len(rows)} ({reason})'
            )
        if not apply or not fixes:
            return

        with transaction.atomic():
            for ln in fixes:
                src = ln.source_routing_line
                ln.work_center_id = src.work_center_id
                ln.work_center_code = (src.work_center_code or src.work_center.code or '')[:40]
            SxSalesOrderRoutingLine.objects.bulk_update(fixes, ['work_center', 'work_center_code'])
        fixed_orders = {ln.sales_order_line.order_id for ln in fixes}
        self.stdout.write(self.style.SUCCESS(
            f'Đã khôi phục {len(fixes)} dòng OB trên {len(fixed_orders)} đơn.'
        ))


def _wc_label(wc) -> str:
    if wc is None:
        return '-'
    return f'{wc.pk}:{wc.name or wc.code}'
