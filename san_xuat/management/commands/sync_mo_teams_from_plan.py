"""Đưa tổ trên bước LSX đang chạy về đúng tổ KHSX (SxSalesOrderPlanStep)."""

from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from san_xuat.hub_models import SxProductionOrder, SxSalesOrder, SxSalesOrderPlanStep, SxWorkCenter
from san_xuat.services.capacity_from_hrm import CODE_PREFIX
from san_xuat.services.plan_board import sync_mo_steps_team


class Command(BaseCommand):
    help = (
        'Gán tổ KHSX cho bước LSX còn giữ tổ cũ (THUÊ NGOÀI, tổ gia công) sau khi '
        'đổi tổ trên lộ trình; mặc định chỉ dry-run, dùng --apply để ghi.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Ghi thay đổi.')
        parser.add_argument('--order-id', type=int, default=0, help='Chỉ xử lý một đơn (id).')

    def handle(self, *args, **options):
        apply = bool(options['apply'])
        # Chỉ sửa bước LSX đang ở tổ không phải bộ phận HR (HRD-*): bước nằm ở
        # bộ phận khác có thể là chủ đích của OB, không suy từ tên công đoạn.
        from_ids = set(
            SxWorkCenter.objects.exclude(code__istartswith=CODE_PREFIX).values_list('pk', flat=True)
        )
        orders = SxSalesOrder.objects.filter(
            is_demo=False,
            production_orders__is_demo=False,
        ).exclude(
            production_orders__status__in=(
                SxProductionOrder.STATUS_CANCELLED, SxProductionOrder.STATUS_DONE,
            ),
        ).distinct()
        if options['order_id']:
            orders = orders.filter(pk=options['order_id'])
        names = dict(SxWorkCenter.objects.values_list('pk', 'name'))
        total = 0
        touched = 0
        with transaction.atomic():
            for order in orders.order_by('pk'):
                plan_steps = list(SxSalesOrderPlanStep.objects.filter(
                    sales_order=order, work_center__isnull=False,
                ))
                wcs_by_name: dict[str, set[int]] = defaultdict(set)
                for step in plan_steps:
                    wcs_by_name[(step.process_name or '').strip().casefold()].add(step.work_center_id)
                by_wc: dict[int, list] = defaultdict(list)
                for step in plan_steps:
                    # Cùng tên công đoạn ở hai tổ trong một đơn thì không đoán.
                    if len(wcs_by_name[(step.process_name or '').strip().casefold()]) == 1:
                        by_wc[step.work_center_id].append(step)
                changed = 0
                for wc_id, steps in by_wc.items():
                    wc = SxWorkCenter.objects.get(pk=wc_id)
                    n = sync_mo_steps_team(order, steps, wc, only_from_ids=from_ids)
                    if n:
                        self.stdout.write(f'  order={order.pk} {order.code}: {n} bước LSX -> {names.get(wc_id)}')
                    changed += n
                if changed:
                    touched += 1
                    total += changed
            mode = 'APPLY' if apply else 'DRY-RUN'
            self.stdout.write(f'[{mode}] {total} bước LSX trên {touched} đơn.')
            if not apply:
                transaction.set_rollback(True)
