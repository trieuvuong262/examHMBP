"""
Xóa toàn bộ dữ liệu menu Tuyển dụng và Kho nguyên phụ liệu.

Chạy local:
  python scripts/clear_recruitment_and_npl.py --yes

Chạy VPS:
  docker compose exec -T -w /app web python scripts/clear_recruitment_and_npl.py --yes
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')


def _setup_django():
    import django
    django.setup()


def count_before() -> dict[str, int]:
    from kho_npl.models import (
        Material,
        MaterialCategory,
        StockAdjustment,
        StockBalance,
        StockDisposal,
        StockIssue,
        StockLedger,
        StockReceipt,
        Stocktake,
        StockTransfer,
        Supplier,
        Unit,
        WarehouseLocation,
    )
    from recruitment.models import Candidate, Interview, JobPosting

    return {
        'job_postings': JobPosting.objects.count(),
        'candidates': Candidate.objects.count(),
        'interviews': Interview.objects.count(),
        'materials': Material.objects.count(),
        'categories': MaterialCategory.objects.count(),
        'units': Unit.objects.count(),
        'locations': WarehouseLocation.objects.count(),
        'suppliers': Supplier.objects.count(),
        'receipts': StockReceipt.objects.count(),
        'issues': StockIssue.objects.count(),
        'transfers': StockTransfer.objects.count(),
        'disposals': StockDisposal.objects.count(),
        'adjustments': StockAdjustment.objects.count(),
        'stocktakes': Stocktake.objects.count(),
        'balances': StockBalance.objects.count(),
        'ledger': StockLedger.objects.count(),
    }


def clear_recruitment() -> dict[str, int]:
    from recruitment.models import Candidate, Interview, JobPosting

    counts = {
        'interviews': Interview.objects.count(),
        'candidates': Candidate.objects.count(),
        'job_postings': JobPosting.objects.count(),
    }
    Interview.objects.all().delete()
    Candidate.objects.all().delete()
    JobPosting.objects.all().delete()
    return counts


def clear_kho_npl() -> dict[str, int]:
    from django.db import transaction

    from kho_npl.models import (
        Material,
        MaterialCategory,
        StockAdjustment,
        StockAdjustmentLine,
        StockBalance,
        StockDisposal,
        StockDisposalLine,
        StockIssue,
        StockIssueLine,
        StockLedger,
        StockReceipt,
        StockReceiptLine,
        Stocktake,
        StocktakeLine,
        StockTransfer,
        StockTransferLine,
        Supplier,
        Unit,
        WarehouseLocation,
    )

    counts = {
        'ledger': StockLedger.objects.count(),
        'stocktake_lines': StocktakeLine.objects.count(),
        'adjustment_lines': StockAdjustmentLine.objects.count(),
        'disposal_lines': StockDisposalLine.objects.count(),
        'transfer_lines': StockTransferLine.objects.count(),
        'issue_lines': StockIssueLine.objects.count(),
        'receipt_lines': StockReceiptLine.objects.count(),
        'stocktakes': Stocktake.objects.count(),
        'adjustments': StockAdjustment.objects.count(),
        'disposals': StockDisposal.objects.count(),
        'transfers': StockTransfer.objects.count(),
        'issues': StockIssue.objects.count(),
        'receipts': StockReceipt.objects.count(),
        'balances': StockBalance.objects.count(),
        'materials': Material.objects.count(),
        'categories': MaterialCategory.objects.count(),
        'units': Unit.objects.count(),
        'locations': WarehouseLocation.objects.count(),
        'suppliers': Supplier.objects.count(),
    }

    with transaction.atomic():
        StockLedger.objects.all().delete()
        StocktakeLine.objects.all().delete()
        StockAdjustmentLine.objects.all().delete()
        StockDisposalLine.objects.all().delete()
        StockTransferLine.objects.all().delete()
        StockIssueLine.objects.all().delete()
        StockReceiptLine.objects.all().delete()
        Stocktake.objects.all().delete()
        StockAdjustment.objects.all().delete()
        StockDisposal.objects.all().delete()
        StockTransfer.objects.all().delete()
        StockIssue.objects.all().delete()
        StockReceipt.objects.all().delete()
        StockBalance.objects.all().delete()
        Material.objects.all().delete()
        MaterialCategory.objects.all().delete()
        Unit.objects.all().delete()
        WarehouseLocation.objects.all().delete()
        Supplier.objects.all().delete()

    return counts


def main():
    parser = argparse.ArgumentParser(description='Xóa dữ liệu Tuyển dụng và/hoặc Kho NPL')
    parser.add_argument('--recruitment-only', action='store_true')
    parser.add_argument('--npl-only', action='store_true')
    parser.add_argument('--yes', action='store_true', help='Xác nhận xóa')
    args = parser.parse_args()

    clear_recruitment_flag = not args.npl_only
    clear_npl_flag = not args.recruitment_only

    _setup_django()

    before = count_before()
    print('Trước khi xóa:')
    for key, val in before.items():
        if val:
            print(f'  {key}: {val}')

    if not args.yes:
        modules = []
        if clear_recruitment_flag:
            modules.append('Tuyển dụng')
        if clear_npl_flag:
            modules.append('Kho nguyên phụ liệu')
        raise SystemExit(f'Thêm --yes để xóa: {", ".join(modules)}')

    if clear_recruitment_flag:
        wiped = clear_recruitment()
        print('Đã xóa Tuyển dụng:', wiped)

    if clear_npl_flag:
        wiped = clear_kho_npl()
        print('Đã xóa Kho NPL:', wiped)

    after = count_before()
    remaining = {k: v for k, v in after.items() if v}
    if remaining:
        print('Còn lại:', remaining)
        return 1
    print('Hoàn tất — không còn dữ liệu.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
