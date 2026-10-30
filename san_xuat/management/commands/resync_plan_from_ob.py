"""Đồng bộ lại lộ trình KHSX + LSX theo OB đơn cho các đơn bị lệch số công đoạn.

Mặc định chỉ liệt kê (dry-run). Thêm --apply để ghi; trước khi ghi luôn backup
plan steps + team day plans + ngày bước LSX ra file JSON.

    python manage.py resync_plan_from_ob                 # liệt kê đơn lệch
    python manage.py resync_plan_from_ob --apply         # đồng bộ tất cả đơn lệch
    python manage.py resync_plan_from_ob --order 166 --apply
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder

from san_xuat.hub_models import (
    SxOrderTeamDayPlan,
    SxSalesOrder,
)


def _ob_count(order: SxSalesOrder) -> int:
    return sum(ln.routing_lines.count() for ln in order.lines.all())


def _backup_rows(order: SxSalesOrder) -> dict:
    mos = []
    for mo in order.production_orders.filter(is_demo=False):
        mos.append({
            'id': mo.pk, 'code': mo.code,
            'planned_start': mo.planned_start, 'planned_end': mo.planned_end,
            'steps': list(mo.mo_process_steps.values()),
        })
    return {
        'order_id': order.pk,
        'code': order.code,
        'plan_start_date': order.plan_start_date,
        'plan_steps': list(order.plan_steps.values()),
        'team_day_plans': list(SxOrderTeamDayPlan.objects.filter(sales_order=order).values()),
        'mos': mos,
    }


class Command(BaseCommand):
    help = 'Đồng bộ lại lộ trình KHSX + LSX theo OB đơn (đơn lệch số công đoạn).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Ghi thay đổi (mặc định chỉ liệt kê).')
        parser.add_argument('--order', type=int, action='append', default=[], help='Chỉ xử lý đơn id này.')
        parser.add_argument('--backup-dir', default='/tmp', help='Thư mục ghi file backup JSON.')

    def handle(self, *args, **opts):
        from san_xuat.services.order_routing import (
            sync_active_mos_from_order,
            sync_order_plan_steps_from_ob,
        )

        qs = SxSalesOrder.objects.filter(
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED, is_demo=False,
        ).exclude(plan_status__in=[
            SxSalesOrder.PLAN_DONE, SxSalesOrder.PLAN_CANCELLED, SxSalesOrder.PLAN_ON_HOLD,
        ])
        if opts['order']:
            qs = qs.filter(pk__in=opts['order'])

        targets = []
        for order in qs.order_by('pk'):
            ob = _ob_count(order)
            plan = order.plan_steps.count()
            if ob and (opts['order'] or ob != plan):
                targets.append((order, ob, plan))
                self.stdout.write(f'{order.pk:>5} {order.code:<24} OB {ob:>3}  KHSX {plan:>3}')

        if not targets:
            self.stdout.write('Không có đơn lệch.')
            return
        if not opts['apply']:
            self.stdout.write(f'Dry-run: {len(targets)} đơn. Thêm --apply để đồng bộ.')
            return

        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = Path(opts['backup_dir']) / f'resync_plan_from_ob_{stamp}.json'
        backup = [_backup_rows(o) for o, _, _ in targets]
        path.write_text(json.dumps(backup, cls=DjangoJSONEncoder, ensure_ascii=False), encoding='utf-8')
        self.stdout.write(f'Backup: {path}')

        ok = 0
        for order, ob, plan in targets:
            try:
                sync_active_mos_from_order(order)
                n = sync_order_plan_steps_from_ob(order)
            except Exception as exc:  # noqa: BLE001 — báo lỗi từng đơn, không dừng cả lô
                self.stderr.write(f'  LỖI {order.code}: {exc}')
                continue
            ok += 1
            self.stdout.write(f'  OK {order.code}: KHSX {plan} -> {n} bước')
        self.stdout.write(f'Xong {ok}/{len(targets)} đơn.')
