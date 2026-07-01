"""
Tạo 30 phiếu nhập / xuất / chuyển / hủy / kiểm kê / điều chỉnh cho JP-BICH-01
để test layout thẻ kho trên local.

Usage:
    python manage.py seed_bich01_stock_card
    python manage.py seed_bich01_stock_card --clear
    python manage.py seed_bich01_stock_card --user admin
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from kho_npl.category_tree import ensure_material_category_tree
from kho_npl.choices import (
    DISPOSAL_REASON_DAMAGED,
    DISPOSAL_REASON_DEFECTIVE,
    DISPOSAL_REASON_EXPIRED,
    DISPOSAL_REASON_OTHER,
    ISSUE_TYPE_PRODUCTION,
    ISSUE_TYPE_SAMPLE,
    ISSUE_TYPE_WASTE,
)
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
from kho_npl.services.adjustments import approve_stock_adjustment
from kho_npl.services.disposals import post_stock_disposal
from kho_npl.services.issues import post_stock_issue
from kho_npl.services.receipts import post_stock_receipt
from kho_npl.services.stocktakes import close_stocktake, populate_stocktake_lines, start_stocktake_counting
from kho_npl.services.transfers import cancel_stock_transfer, receive_stock_transfer, send_stock_transfer
from kho_npl.services.stock import sync_balances_from_ledger
from kho_npl.services.stock_card import recalculate_ledger_balances

MATERIAL_CODE = 'JP-BICH-01'
MATERIAL_NAME = 'Bịch kính OPP 24'
TAG = 'BICH01'
DEMO_NOTE = f'Dữ liệu test thẻ kho ({TAG}) — {MATERIAL_CODE}'

DEMO_ATTACHMENT = ContentFile(b'%PDF-1.4 demo attachment for stock card seed\n', name='chung-tu-demo.pdf')


def _num(prefix: str, seq: int) -> str:
    return f'{prefix}-{TAG}-2026-{seq:03d}'


def _attach(file_field) -> None:
    file_field.save('chung-tu-demo.pdf', DEMO_ATTACHMENT, save=True)


def _aware_date(d):
    return timezone.make_aware(datetime.combine(d, time(9, 0)))


class Command(BaseCommand):
    help = f'Seed 30 chứng từ kho NPL cho {MATERIAL_CODE} (test thẻ kho).'

    def add_arguments(self, parser):
        parser.add_argument('--user', default='admin', help='Username tạo/ghi sổ phiếu')
        parser.add_argument('--clear', action='store_true', help=f'Xóa phiếu có mã chứa -{TAG}-')

    def handle(self, *args, **options):
        if options['clear']:
            self._clear()
            return

        user = self._resolve_user(options['user'])
        today = timezone.localdate()

        with transaction.atomic():
            material = self._ensure_material()
            loc_b2 = self._location('KE-B2')
            loc_pl = self._location('KHO-PL')
            loc_xs = self._location('XUONG-SX')
            supplier = self._supplier('NCC-BAOBI-TG')

            if StockReceipt.objects.filter(number__contains=f'-{TAG}-').exists():
                self.stdout.write(self.style.WARNING(
                    f'Đã có phiếu -{TAG}-. Chạy --clear trước hoặc bỏ qua.',
                ))
                return

            created = 0
            created += self._seed_receipts(user, today, material, supplier, loc_b2, loc_pl)
            created += self._seed_issues(user, today, material, loc_b2, loc_pl)
            created += self._seed_transfers(user, today, material, loc_b2, loc_pl, loc_xs)
            created += self._seed_disposals(user, today, material, loc_b2)
            created += self._seed_stocktakes(user, today, material, loc_b2)
            created += self._seed_adjustments(user, today, material, loc_b2, loc_pl)
            self._backdate_ledgers(material)
            fixed = recalculate_ledger_balances(material)
            if fixed:
                self.stdout.write(f'  Đã chuẩn hóa {fixed} dòng sổ kho (balance_after).')
            synced = sync_balances_from_ledger(material)
            if synced:
                self.stdout.write(f'  Đã đồng bộ {synced} dòng tồn kho từ sổ.')

        self.stdout.write(self.style.SUCCESS(
            f'\n==> Đã tạo {created} phiếu cho {MATERIAL_CODE}',
        ))
        self.stdout.write(
            f'  Thẻ kho: /kho-npl/the-kho/?material={material.pk}',
        )
        self.stdout.write(self.style.WARNING(
            f'\nXóa: python manage.py seed_bich01_stock_card --clear',
        ))

    def _resolve_user(self, username: str):
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.filter(is_superuser=True).order_by('id').first()
        if not user:
            raise CommandError('Không tìm thấy user. Tạo superuser hoặc truyền --user.')
        return user

    def _ensure_material(self) -> Material:
        ensure_material_category_tree()
        unit, _ = Unit.objects.get_or_create(code='cai', defaults={'name': 'Cái'})
        category = MaterialCategory.objects.filter(code='bao-bi').first()
        supplier = self._supplier('NCC-BAOBI-TG')
        material, created = Material.objects.get_or_create(
            code=MATERIAL_CODE,
            defaults={
                'name': MATERIAL_NAME,
                'category': category,
                'unit': unit,
                'color': 'Trong',
                'specification': 'OPP 24cm',
                'supplier': supplier,
                'min_stock': Decimal('500'),
                'is_active': True,
            },
        )
        if created:
            self.stdout.write(f'  + NPL {MATERIAL_CODE}')
        return material

    def _location(self, code: str) -> WarehouseLocation:
        loc = WarehouseLocation.objects.filter(code=code).first()
        if not loc:
            raise CommandError(
                f'Chưa có vị trí kho {code}. Chạy seed_kho_npl_demo hoặc tạo vị trí trước.',
            )
        return loc

    def _supplier(self, code: str) -> Supplier:
        supplier, _ = Supplier.objects.get_or_create(
            code=code,
            defaults={'name': code, 'phone': ''},
        )
        return supplier

    def _seed_receipts(self, user, today, material, supplier, loc_b2, loc_pl) -> int:
        specs = [
            (_num('PN', 1), 95, loc_b2, Decimal('2000'), 'PO-BICH-2401'),
            (_num('PN', 2), 88, loc_b2, Decimal('1500'), 'PO-BICH-2402'),
            (_num('PN', 3), 82, loc_pl, Decimal('1000'), 'PO-BICH-2403'),
            (_num('PN', 4), 76, loc_b2, Decimal('800'), 'PO-BICH-2404'),
            (_num('PN', 5), 70, loc_b2, Decimal('600'), 'PO-BICH-2405'),
            (_num('PN', 6), 64, loc_b2, Decimal('400'), 'PO-BICH-2406'),
            (_num('PN', 7), 58, loc_b2, Decimal('300'), 'PO-BICH-2407'),
        ]
        count = 0
        for number, days_ago, location, qty, po in specs:
            receipt = StockReceipt.objects.create(
                number=number,
                receipt_date=today - timedelta(days=days_ago),
                supplier=supplier,
                po_number=po,
                received_by=user,
                created_by=user,
                notes=DEMO_NOTE,
            )
            StockReceiptLine.objects.create(
                receipt=receipt,
                material=material,
                ordered_qty=qty,
                received_qty=qty,
                location=location,
            )
            _attach(receipt.attachment)
            post_stock_receipt(receipt, user)
            count += 1
        return count

    def _seed_issues(self, user, today, material, loc_b2, loc_pl) -> int:
        specs = [
            (_num('PX', 1), 90, loc_b2, Decimal('500'), ISSUE_TYPE_PRODUCTION, 'LSX-JP-001'),
            (_num('PX', 2), 84, loc_b2, Decimal('400'), ISSUE_TYPE_PRODUCTION, 'LSX-JP-002'),
            (_num('PX', 3), 78, loc_b2, Decimal('350'), ISSUE_TYPE_SAMPLE, ''),
            (_num('PX', 4), 72, loc_b2, Decimal('300'), ISSUE_TYPE_PRODUCTION, 'LSX-JP-003'),
            (_num('PX', 5), 66, loc_b2, Decimal('250'), ISSUE_TYPE_WASTE, ''),
            (_num('PX', 6), 60, loc_pl, Decimal('200'), ISSUE_TYPE_PRODUCTION, 'LSX-JP-004'),
            (_num('PX', 7), 54, loc_b2, Decimal('150'), ISSUE_TYPE_SAMPLE, ''),
        ]
        count = 0
        for number, days_ago, location, qty, issue_type, po in specs:
            issue = StockIssue.objects.create(
                number=number,
                issue_date=today - timedelta(days=days_ago),
                issue_type=issue_type,
                production_order=po,
                recipient_department='Xưởng may',
                recipient_name='Tổ trưởng A',
                issued_by=user,
                created_by=user,
                notes=DEMO_NOTE,
            )
            StockIssueLine.objects.create(
                issue=issue,
                material=material,
                quantity=qty,
                location=location,
            )
            _attach(issue.attachment)
            post_stock_issue(issue, user)
            count += 1
        return count

    def _seed_transfers(self, user, today, material, loc_b2, loc_pl, loc_xs) -> int:
        count = 0

        t1 = StockTransfer.objects.create(
            number=_num('PC', 1),
            transfer_date=today - timedelta(days=80),
            from_location=loc_b2,
            to_location=loc_pl,
            created_by=user,
            notes=f'Chuyển bịch sang kho PL — {DEMO_NOTE}',
        )
        StockTransferLine.objects.create(transfer=t1, material=material, quantity=Decimal('200'))
        send_stock_transfer(t1, user)
        receive_stock_transfer(t1, user)
        count += 1

        t2 = StockTransfer.objects.create(
            number=_num('PC', 2),
            transfer_date=today - timedelta(days=68),
            from_location=loc_b2,
            to_location=loc_pl,
            created_by=user,
            notes=DEMO_NOTE,
        )
        StockTransferLine.objects.create(transfer=t2, material=material, quantity=Decimal('150'))
        send_stock_transfer(t2, user)
        receive_stock_transfer(t2, user)
        count += 1

        t3 = StockTransfer.objects.create(
            number=_num('PC', 3),
            transfer_date=today - timedelta(days=56),
            from_location=loc_b2,
            to_location=loc_xs,
            created_by=user,
            notes='Chuyển xuống xưởng SX',
        )
        StockTransferLine.objects.create(transfer=t3, material=material, quantity=Decimal('100'))
        send_stock_transfer(t3, user)
        receive_stock_transfer(t3, user)
        count += 1

        t4 = StockTransfer.objects.create(
            number=_num('PC', 4),
            transfer_date=today - timedelta(days=48),
            from_location=loc_b2,
            to_location=loc_pl,
            created_by=user,
            notes='Đang vận chuyển — demo trạng thái',
        )
        StockTransferLine.objects.create(transfer=t4, material=material, quantity=Decimal('80'))
        send_stock_transfer(t4, user)
        count += 1

        t5 = StockTransfer.objects.create(
            number=_num('PC', 5),
            transfer_date=today - timedelta(days=42),
            from_location=loc_b2,
            to_location=loc_pl,
            created_by=user,
            notes='Phiếu nháp bị hủy',
        )
        StockTransferLine.objects.create(transfer=t5, material=material, quantity=Decimal('50'))
        cancel_stock_transfer(t5)
        count += 1

        return count

    def _seed_disposals(self, user, today, material, loc_b2) -> int:
        reasons = [
            DISPOSAL_REASON_DAMAGED,
            DISPOSAL_REASON_DEFECTIVE,
            DISPOSAL_REASON_EXPIRED,
            DISPOSAL_REASON_OTHER,
        ]
        qtys = [Decimal('30'), Decimal('25'), Decimal('20'), Decimal('15')]
        count = 0
        for idx, (reason, qty) in enumerate(zip(reasons, qtys), start=1):
            disposal = StockDisposal.objects.create(
                number=_num('PH', idx),
                disposal_date=today - timedelta(days=74 - idx * 4),
                from_location=loc_b2,
                reason=reason,
                created_by=user,
                notes=f'Hủy bịch rách / lỗi in — {DEMO_NOTE}',
            )
            StockDisposalLine.objects.create(
                disposal=disposal,
                material=material,
                quantity=qty,
                notes='Lô demo',
            )
            post_stock_disposal(disposal, user)
            count += 1
        return count

    def _seed_stocktakes(self, user, today, material, loc_b2) -> int:
        count = 0

        st1 = Stocktake.objects.create(
            number=_num('KK', 1),
            name=f'Kiểm kê KE-B2 — {MATERIAL_CODE}',
            stocktake_date=today - timedelta(days=50),
            location=loc_b2,
            created_by=user,
            notes=DEMO_NOTE,
        )
        populate_stocktake_lines(st1)
        start_stocktake_counting(st1)
        for line in st1.lines.all():
            if line.material_id == material.pk:
                line.actual_qty = max(Decimal('0'), line.system_qty - Decimal('2'))
            else:
                line.actual_qty = line.system_qty
            line.save(update_fields=['actual_qty'])
        close_stocktake(st1, user)
        count += 1

        st2 = Stocktake.objects.create(
            number=_num('KK', 2),
            name=f'Kiểm kê bao bì Q2 — {MATERIAL_CODE}',
            stocktake_date=today - timedelta(days=38),
            location=loc_b2,
            created_by=user,
            notes=DEMO_NOTE,
        )
        populate_stocktake_lines(st2)
        start_stocktake_counting(st2)
        for line in st2.lines.all():
            if line.material_id == material.pk:
                line.actual_qty = line.system_qty + Decimal('3')
            else:
                line.actual_qty = line.system_qty
            line.save(update_fields=['actual_qty'])
        close_stocktake(st2, user)
        count += 1

        Stocktake.objects.create(
            number=_num('KK', 3),
            name=f'Kiểm kê nháp — {MATERIAL_CODE}',
            stocktake_date=today - timedelta(days=12),
            location=loc_b2,
            created_by=user,
            notes='Phiếu kiểm kê nháp (chưa bắt đầu đếm)',
        )
        count += 1

        return count

    def _seed_adjustments(self, user, today, material, loc_b2, loc_pl) -> int:
        count = 0
        specs = [
            (_num('DC', 1), 46, loc_b2, Decimal('-5'), 'Thiếu 5 bịch sau kiểm kê', True),
            (_num('DC', 2), 40, loc_b2, Decimal('10'), 'Thừa 10 bịch — nhập nhầm chưa ghi sổ', True),
            (_num('DC', 3), 34, loc_pl, Decimal('8'), 'Điều chỉnh tồn kho PL', True),
            (_num('DC', 4), 28, loc_b2, Decimal('2'), 'Chờ duyệt — phát hiện thêm 2 bịch', False),
        ]
        for number, days_ago, location, delta, reason, do_approve in specs:
            balance = StockBalance.objects.filter(material=material, location=location).first()
            system_qty = balance.quantity if balance else Decimal('0')
            actual_qty = max(Decimal('0'), system_qty + delta)
            adj = StockAdjustment.objects.create(
                number=number,
                adjust_date=today - timedelta(days=days_ago),
                reason=f'{reason} — {DEMO_NOTE}',
                proposed_by=user,
            )
            StockAdjustmentLine.objects.create(
                adjustment=adj,
                material=material,
                location=location,
                system_qty=system_qty,
                actual_qty=actual_qty,
            )
            if do_approve:
                approve_stock_adjustment(adj, user)
            count += 1
        return count

    def _backdate_ledgers(self, material: Material) -> None:
        """Gán created_at sổ kho theo ngày chứng từ để lọc ngày trên thẻ kho có ý nghĩa."""
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

    @transaction.atomic
    def _clear(self):
        self.stdout.write(self.style.WARNING(f'==> Xóa phiếu -{TAG}-...'))
        tag_filter = {'number__contains': f'-{TAG}-'}
        material = Material.objects.filter(code=MATERIAL_CODE).first()
        if material:
            StockLedger.objects.filter(material=material, ref_number__contains=f'-{TAG}-').delete()
            StocktakeLine.objects.filter(material=material, stocktake__number__contains=f'-{TAG}-').delete()
        StockAdjustment.objects.filter(**tag_filter).delete()
        StockDisposal.objects.filter(**tag_filter).delete()
        StockTransfer.objects.filter(**tag_filter).delete()
        StockIssue.objects.filter(**tag_filter).delete()
        StockReceipt.objects.filter(**tag_filter).delete()
        Stocktake.objects.filter(**tag_filter).delete()
        if material:
            sync_balances_from_ledger(material)
        self.stdout.write(self.style.SUCCESS('  Đã xóa.'))
