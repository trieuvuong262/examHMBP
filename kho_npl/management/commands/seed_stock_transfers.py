"""
Tạo phiếu chuyển kho test trên VPS/local.

Usage:
    python manage.py seed_stock_transfers --count 100
    python manage.py seed_stock_transfers --count 100 --clear
    python manage.py seed_stock_transfers --clear-only
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from kho_npl.choices import (
    TRANSFER_STATUS_DRAFT,
    TRANSFER_STATUS_IN_TRANSIT,
    TRANSFER_STATUS_RECEIVED,
)
from kho_npl.models import (
    Material,
    StockBalance,
    StockLedger,
    StockReceipt,
    StockReceiptLine,
    StockTransfer,
    StockTransferLine,
    WarehouseLocation,
)
from kho_npl.services.doc_numbers import next_transfer_number
from kho_npl.services.receipts import post_stock_receipt
from kho_npl.services.transfers import (
    TransferWorkflowError,
    receive_stock_transfer,
    send_stock_transfer,
)

SEED_NOTE = 'SEED:stock-transfer-test'
SEED_OPENING_NOTE = 'SEED:stock-opening-for-transfer-test'
OPENING_RECEIPT_PREFIX = 'PN-SEED-OPEN'


class Command(BaseCommand):
    help = 'Tạo phiếu chuyển kho mẫu (nháp / đang chuyển / đã nhập).'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100, help='Số phiếu cần tạo (mặc định 100)')
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Xóa dữ liệu seed chuyển kho + tồn mở đầu seed trước khi tạo',
        )
        parser.add_argument(
            '--clear-only',
            action='store_true',
            help='Chỉ xóa dữ liệu seed chuyển kho / tồn mở đầu (không tạo mới)',
        )
        parser.add_argument(
            '--opening-qty',
            type=int,
            default=500000,
            help='Số lượng tồn mở đầu mỗi NPL×kệ qua phiếu nhập (mặc định 500000)',
        )

    def handle(self, *args, **options):
        if options['clear_only']:
            self._clear_seed_data()
            return

        count = max(1, options['count'])
        opening_qty = Decimal(str(max(100, options['opening_qty'])))
        User = get_user_model()
        user = User.objects.filter(username='admin').first() or User.objects.filter(is_superuser=True).first()
        if not user:
            raise CommandError('Không tìm thấy user admin/superuser.')

        if options['clear']:
            self._clear_seed_data()

        locations = list(WarehouseLocation.objects.filter(is_active=True).order_by('code'))
        if len(locations) < 2:
            raise CommandError('Cần ít nhất 2 kho hoạt động.')

        materials = list(
            Material.objects.filter(is_active=True).select_related('unit').order_by('code')[:80],
        )
        if not materials:
            raise CommandError('Chưa có nguyên phụ liệu — chạy migrate/seed kho NPL trước.')

        self._ensure_stock(user, materials, locations, opening_qty)

        n_draft = count // 3
        n_transit = count // 3
        n_received = count - n_draft - n_transit
        plan = (
            [(TRANSFER_STATUS_DRAFT, n_draft)]
            + [(TRANSFER_STATUS_IN_TRANSIT, n_transit)]
            + [(TRANSFER_STATUS_RECEIVED, n_received)]
        )

        created = 0
        errors = 0
        for target_status, qty in plan:
            for _ in range(qty):
                for _attempt in range(8):
                    try:
                        self._create_transfer(user, materials, locations, target_status)
                        created += 1
                        if created % 10 == 0:
                            self.stdout.write(f'  … {created}/{count}')
                        break
                    except (TransferWorkflowError, CommandError) as exc:
                        if _attempt == 7:
                            errors += 1
                            self.stderr.write(self.style.ERROR(str(exc)))

        self.stdout.write(self.style.SUCCESS(
            f'Hoàn tất: {created} phiếu chuyển test'
            + (f' ({errors} lỗi bỏ qua)' if errors else ''),
        ))

    @transaction.atomic
    def _clear_seed_data(self):
        self.stdout.write(self.style.WARNING('==> Xóa dữ liệu seed chuyển kho / tồn mở đầu...'))

        transfer_ids = list(
            StockTransfer.objects.filter(notes=SEED_NOTE).values_list('pk', flat=True),
        )
        if transfer_ids:
            StockLedger.objects.filter(
                ref_type=StockLedger.REF_TRANSFER,
                ref_id__in=transfer_ids,
            ).delete()
            deleted, _ = StockTransfer.objects.filter(pk__in=transfer_ids).delete()
            self.stdout.write(f'  Đã xóa {deleted} phiếu chuyển seed.')

        opening_ids = list(
            StockReceipt.objects.filter(notes=SEED_OPENING_NOTE).values_list('pk', flat=True),
        )
        if opening_ids:
            StockLedger.objects.filter(
                ref_type=StockLedger.REF_RECEIPT,
                ref_id__in=opening_ids,
            ).delete()
            StockReceiptLine.objects.filter(receipt_id__in=opening_ids).delete()
            deleted, _ = StockReceipt.objects.filter(pk__in=opening_ids).delete()
            self.stdout.write(f'  Đã xóa {deleted} phiếu nhập tồn mở đầu seed.')

        material_ids = list(
            Material.objects.filter(is_active=True).order_by('code').values_list('pk', flat=True)[:80],
        )
        if material_ids:
            self._rebuild_balances_from_ledger(material_ids)
            self.stdout.write(f'  Đã đồng bộ lại tồn từ sổ cho {len(material_ids)} NPL đầu danh mục.')

        self.stdout.write(self.style.SUCCESS('Xóa seed chuyển kho xong.'))

    def _rebuild_balances_from_ledger(self, material_ids):
        StockBalance.objects.filter(material_id__in=material_ids).delete()
        totals = (
            StockLedger.objects.filter(material_id__in=material_ids)
            .values('material_id', 'location_id')
            .annotate(total=Sum('qty_delta'))
        )
        batch = []
        for row in totals:
            total = row['total'] or Decimal('0')
            if total == 0:
                continue
            batch.append(StockBalance(
                material_id=row['material_id'],
                location_id=row['location_id'],
                quantity=total,
            ))
        if batch:
            StockBalance.objects.bulk_create(batch, batch_size=500)

    def _ensure_stock(self, user, materials, locations, target_qty: Decimal):
        """Bổ sung tồn qua phiếu nhập có ghi sổ — không ghi thẳng StockBalance."""
        posted = 0
        for loc in locations:
            lines = []
            for mat in materials:
                bal = StockBalance.objects.filter(material=mat, location=loc).first()
                current = bal.quantity if bal else Decimal('0')
                if current >= target_qty:
                    continue
                lines.append((mat, target_qty - current))
            if not lines:
                continue

            receipt = StockReceipt.objects.create(
                number=self._opening_receipt_number(loc),
                receipt_date=timezone.localdate(),
                received_by=user,
                checked_by=user,
                created_by=user,
                notes=SEED_OPENING_NOTE,
            )
            StockReceiptLine.objects.bulk_create([
                StockReceiptLine(
                    receipt=receipt,
                    material=mat,
                    location=loc,
                    ordered_qty=qty,
                    received_qty=qty,
                )
                for mat, qty in lines
            ])
            post_stock_receipt(receipt, user)
            posted += 1
            self.stdout.write(
                f'  Nhập mở đầu {loc.code}: {len(lines)} dòng (ghi sổ {receipt.number})',
            )
        if posted:
            self.stdout.write(self.style.SUCCESS(f'  Đã ghi sổ {posted} phiếu nhập tồn mở đầu.'))

    def _opening_receipt_number(self, location: WarehouseLocation) -> str:
        year = timezone.localdate().year
        base = f'{OPENING_RECEIPT_PREFIX}-{location.code}-{year}'
        if not StockReceipt.objects.filter(number=base).exists():
            return base
        seq = 2
        while StockReceipt.objects.filter(number=f'{base}-{seq}').exists():
            seq += 1
        return f'{base}-{seq}'

    def _pick_line(self, from_loc, materials, min_qty: Decimal):
        stocked = list(
            StockBalance.objects.filter(
                location=from_loc,
                material__in=materials,
                quantity__gte=min_qty,
            ).select_related('material')[:40],
        )
        if not stocked:
            raise CommandError(f'Không có tồn đủ tại {from_loc.code}.')
        pick = random.choice(stocked)
        max_qty = min(pick.quantity, Decimal('50'))
        qty = Decimal(str(random.randint(1, int(max_qty))))
        if qty < min_qty:
            qty = min_qty
        return pick.material, qty

    @transaction.atomic
    def _create_transfer(self, user, materials, locations, target_status: str):
        from_loc, to_loc = random.sample(locations, 2)
        min_qty = Decimal('1')
        mat, qty = self._pick_line(from_loc, materials, min_qty)
        transfer_date = timezone.localdate() - timedelta(days=random.randint(0, 60))
        transfer = StockTransfer.objects.create(
            number=next_transfer_number(),
            transfer_date=transfer_date,
            from_location=from_loc,
            to_location=to_loc,
            created_by=user,
            notes=SEED_NOTE,
            status=TRANSFER_STATUS_DRAFT,
        )
        StockTransferLine.objects.create(transfer=transfer, material=mat, quantity=qty, notes='Dòng test')

        if target_status == TRANSFER_STATUS_DRAFT:
            return transfer

        send_stock_transfer(transfer, user)
        if target_status == TRANSFER_STATUS_IN_TRANSIT:
            return transfer

        receive_stock_transfer(transfer, user)
        return transfer
