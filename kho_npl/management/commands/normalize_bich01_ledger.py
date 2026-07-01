"""Chuẩn hóa sổ kho JP-BICH-01: backdate theo ngày chứng từ + tính lại balance_after."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from kho_npl.management.commands.seed_bich01_stock_card import MATERIAL_CODE
from kho_npl.models import (
    Material,
    StockAdjustment,
    StockDisposal,
    StockIssue,
    StockLedger,
    StockReceipt,
    Stocktake,
    StockTransfer,
)
from kho_npl.services.stock import sync_balances_from_ledger
from kho_npl.services.stock_card import recalculate_ledger_balances

TAG = 'BICH01'


def _aware_date(d):
    return timezone.make_aware(datetime.combine(d, time(9, 0)))


def backdate_material_ledgers(material: Material) -> None:
    ref_date_map = {}
    for receipt in StockReceipt.objects.filter(lines__material=material).distinct():
        ref_date_map[(StockLedger.REF_RECEIPT, receipt.pk)] = receipt.receipt_date
    for issue in StockIssue.objects.filter(lines__material=material).distinct():
        ref_date_map[(StockLedger.REF_ISSUE, issue.pk)] = issue.issue_date
    for transfer in StockTransfer.objects.filter(lines__material=material).distinct():
        ref_date_map[(StockLedger.REF_TRANSFER, transfer.pk)] = transfer.transfer_date
    for disposal in StockDisposal.objects.filter(lines__material=material).distinct():
        ref_date_map[(StockLedger.REF_DISPOSAL, disposal.pk)] = disposal.disposal_date
    for st in Stocktake.objects.filter(lines__material=material).distinct():
        ref_date_map[(StockLedger.REF_STOCKTAKE, st.pk)] = st.stocktake_date
    for adj in StockAdjustment.objects.filter(lines__material=material).distinct():
        ref_date_map[(StockLedger.REF_ADJUSTMENT, adj.pk)] = adj.adjust_date

    offset_minutes = 0
    for ledger in StockLedger.objects.filter(material=material).order_by('id'):
        doc_date = ref_date_map.get((ledger.ref_type, ledger.ref_id))
        if not doc_date:
            continue
        offset_minutes += 1
        ledger.created_at = _aware_date(doc_date) + timedelta(minutes=offset_minutes)
        ledger.save(update_fields=['created_at'])


class Command(BaseCommand):
    help = f'Chuẩn hóa sổ kho {MATERIAL_CODE} (backdate + balance_after lũy kế).'

    @transaction.atomic
    def handle(self, *args, **options):
        material = Material.objects.filter(code=MATERIAL_CODE).first()
        if not material:
            raise CommandError(f'Không tìm thấy NPL {MATERIAL_CODE}.')

        has_tag = StockReceipt.objects.filter(number__contains=f'-{TAG}-').exists()
        if not has_tag:
            raise CommandError(
                f'Chưa có phiếu -{TAG}-. Chạy: python manage.py seed_bich01_stock_card',
            )

        backdate_material_ledgers(material)
        fixed = recalculate_ledger_balances(material)
        synced = sync_balances_from_ledger(material)
        self.stdout.write(self.style.SUCCESS(
            f'Đã chuẩn hóa {MATERIAL_CODE}: {fixed} dòng balance_after, {synced} dòng tồn kho.',
        ))
