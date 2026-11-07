"""Tạo / cập nhật LSX nháp cho đơn đã xác nhận đang Chờ xếp hoặc Tạm giữ.

Mặc định chỉ chạy thử (rollback). Thêm --apply để ghi.

    python manage.py sync_order_draft_mos                 # chạy thử tất cả đơn chờ xếp
    python manage.py sync_order_draft_mos --apply
    python manage.py sync_order_draft_mos --order 225 --apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from san_xuat.hub_models import SxProductionOrder, SxSalesOrder
from san_xuat.services.order_draft_mo import DRAFT_PLAN_STATUSES, sync_order_draft_mos


class Command(BaseCommand):
    help = 'Tạo / cập nhật LSX nháp cho đơn đang Chờ xếp / Tạm giữ trên KHSX.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Ghi thay đổi (mặc định chỉ chạy thử).')
        parser.add_argument('--order', type=int, action='append', default=[], help='Chỉ xử lý đơn id này.')

    def handle(self, *args, **opts):
        qs = SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status__in=DRAFT_PLAN_STATUSES,
        )
        if opts['order']:
            qs = qs.filter(pk__in=opts['order'])

        total = created = updated = cancelled = 0
        for order in qs.order_by('pk'):
            total += 1
            try:
                with transaction.atomic():
                    result = sync_order_draft_mos(order.pk)
                    mos = list(
                        SxProductionOrder.objects.filter(sales_order_id=order.pk, is_demo=False)
                        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
                        .order_by('pk')
                        .values_list('code', 'status')
                    )
                    if not opts['apply']:
                        transaction.set_rollback(True)
            except Exception as exc:  # noqa: BLE001 — báo lỗi từng đơn, không dừng cả lô
                self.stderr.write(f'  LỖI {order.code}: {exc}')
                continue
            created += result.created
            updated += result.updated
            cancelled += result.cancelled
            drafts = [code for code, st in mos if st == SxProductionOrder.STATUS_DRAFT]
            started = [code for code, st in mos if st != SxProductionOrder.STATUS_DRAFT]
            if drafts:
                status = 'nháp: ' + ', '.join(drafts)
            elif started:
                status = 'đã có LSX: ' + ', '.join(started)
            else:
                status = 'chưa đủ BOM / công đoạn'
            self.stdout.write(
                f'{order.pk:>5} {order.code:<28} +{result.created} ~{result.updated} '
                f'-{result.cancelled}  {status}'
            )

        mode = 'Đã ghi' if opts['apply'] else 'Chạy thử (không ghi, thêm --apply để ghi)'
        self.stdout.write(
            f'{mode}: {total} đơn, tạo {created}, cập nhật {updated}, hủy {cancelled} LSX nháp.'
        )
