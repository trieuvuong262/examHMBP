"""
Tạo phiếu chuyển kho test trên VPS/local.

Usage:
    python manage.py seed_stock_transfers --count 100
    python manage.py seed_stock_transfers --count 100 --clear
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from kho_npl.choices import (
    TRANSFER_STATUS_DRAFT,
    TRANSFER_STATUS_IN_TRANSIT,
    TRANSFER_STATUS_RECEIVED,
)
from kho_npl.models import Material, StockBalance, StockTransfer, StockTransferLine, WarehouseLocation
from kho_npl.services.doc_numbers import next_transfer_number
from kho_npl.services.transfers import (
    TransferWorkflowError,
    receive_stock_transfer,
    send_stock_transfer,
)

SEED_NOTE = 'SEED:stock-transfer-test'


class Command(BaseCommand):
    help = 'Tạo phiếu chuyển kho mẫu (nháp / đang chuyển / đã nhập).'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100, help='Số phiếu cần tạo (mặc định 100)')
        parser.add_argument(
            '--clear',
            action='store_true',
            help=f'Xóa phiếu có ghi chú "{SEED_NOTE}" trước khi tạo',
        )

    def handle(self, *args, **options):
        count = max(1, options['count'])
        User = get_user_model()
        user = User.objects.filter(username='admin').first() or User.objects.filter(is_superuser=True).first()
        if not user:
            raise CommandError('Không tìm thấy user admin/superuser.')

        if options['clear']:
            deleted, _ = StockTransfer.objects.filter(notes=SEED_NOTE).delete()
            self.stdout.write(self.style.WARNING(f'Đã xóa {deleted} phiếu seed cũ.'))

        locations = list(WarehouseLocation.objects.filter(is_active=True).order_by('code'))
        if len(locations) < 2:
            raise CommandError('Cần ít nhất 2 kho hoạt động.')

        materials = list(
            Material.objects.filter(is_active=True).select_related('unit').order_by('code')[:80],
        )
        if not materials:
            raise CommandError('Chưa có nguyên phụ liệu — chạy migrate/seed kho NPL trước.')

        self._ensure_stock(materials, locations)

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
                ok = False
                for _attempt in range(8):
                    try:
                        self._create_transfer(user, materials, locations, target_status)
                        created += 1
                        ok = True
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

    def _ensure_stock(self, materials, locations):
        qty = Decimal('500000')
        for loc in locations:
            for mat in materials:
                balance, created = StockBalance.objects.get_or_create(
                    material=mat,
                    location=loc,
                    defaults={'quantity': qty},
                )
                if not created and balance.quantity < qty:
                    balance.quantity = qty
                    balance.save(update_fields=['quantity', 'updated_at'])

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
