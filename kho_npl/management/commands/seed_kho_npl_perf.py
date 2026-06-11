"""
Tạo dữ liệu tồn kho NPL quy mô lớn để test hiệu năng trên VPS.

Usage:
    python manage.py seed_kho_npl_perf
    python manage.py seed_kho_npl_perf --materials 2500 --receipts 600 --issues 2000
    python manage.py seed_kho_npl_perf --clear
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from kho_npl.choices import (
    ADJUST_STATUS_PENDING,
    ADJUST_STATUS_REJECTED,
    ISSUE_TYPE_CHOICES,
    ISSUE_TYPE_PRODUCTION,
)
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    StockIssue,
    StockIssueLine,
    StockLedger,
    StockReceipt,
    StockReceiptLine,
    Stocktake,
    StocktakeLine,
    StockTransfer,
    Supplier,
    Unit,
    WarehouseLocation,
)
from kho_npl.services.adjustments import approve_stock_adjustment, reject_stock_adjustment
from kho_npl.services.issues import post_stock_issue
from kho_npl.services.receipts import post_stock_receipt
from kho_npl.services.stocktakes import close_stocktake, start_stocktake_counting

PERF_TAG = 'PERF'
MATERIAL_PREFIX = 'PERF-'
SEED_TRANSFER_NOTE = 'SEED:stock-transfer-test'
SEED_OPENING_NOTE = 'SEED:stock-opening-for-transfer-test'

EXTRA_LOCATIONS = [
    ('KE-A1', 'Kệ A1 — Vải chính'),
    ('KE-A2', 'Kệ A2 — Vải phối'),
    ('KE-B1', 'Kệ B1 — Phụ liệu may'),
    ('KE-B2', 'Kệ B2 — Tem / bao bì'),
    ('XUONG-SX', 'Kho xưởng sản xuất'),
    ('KHO-PL', 'Kho phụ liệu lẻ'),
]

SUPPLIERS = [
    ('NCC-VAI-DONGNAI', 'Công ty TNHH Vải Đồng Nai', '0903123456'),
    ('NCC-VAI-HCM', 'Vải Thành Công — TP.HCM', '02838234567'),
    ('NCC-PHULIEU-BD', 'Phụ liệu May Bình Dương', '02743891234'),
    ('NCC-YKK-VN', 'YKK Việt Nam — Dây kéo', '02837778899'),
    ('NCC-TEM-HN', 'In Tem Hà Nội', '02435678901'),
    ('NCC-BAOBI-TG', 'Bao bì Tiền Giang', '02733881234'),
    ('NCC-CHI-POLY', 'Chỉ Polyester Đại Phát', '0908765432'),
    ('NCC-DECAL-SG', 'Decal Heat Transfer Sài Gòn', '0909111222'),
    ('NCC-NUT-KHOEN', 'Nút Khoen Minh Phát', '0905333444'),
    ('NCC-VAI-THAI', 'Vải Nhập Thái Lan (đại lý)', '0906555666'),
    ('NCC-RIB-CO', 'Bo cổ Bo tay Cô Tâm', '0907777888'),
    ('NCC-TUI-OPP', 'Túi OPP Bình Minh', '0908999000'),
]

# (category_code, unit_code, name_templates, colors, specs)
MATERIAL_BLUEPRINTS = [
    (
        'vai-chinh', 'met',
        [
            'Vải cotton 100% {gsm}gsm',
            'Vải polyester spandex 4 chiều {gsm}gsm',
            'Vải French Terry {gsm}gsm',
            'Vải pique cotton {gsm}gsm',
            'Vải interlock cotton {gsm}gsm',
            'Vải fleece nỉ bông {gsm}gsm',
            'Vải linen pha cotton {gsm}gsm',
        ],
        ['Trắng', 'Đen', 'Navy', 'Xám melange', 'Be', 'Đỏ đô', 'Xanh rêu', 'Hồng pastel'],
        ['Khổ 1m6', 'Khổ 1m7', 'Khổ 1m8', 'Khổ 72"', 'Khổ 60"'],
    ),
    (
        'vai-phoi', 'met',
        [
            'Vải rib 1x1 cổ áo',
            'Vải rib 2x2 bo tay',
            'Vải lót polyester',
            'Vải thun cotton phối',
            'Vải mesh thoáng',
        ],
        ['Trắng', 'Đen', 'Navy', 'Xám', 'Đỏ'],
        ['Khổ 30cm', 'Khổ 40cm', 'Khổ 1m2', 'Khổ 1m5'],
    ),
    (
        'bo-co-tay', 'cuon',
        [
            'Bo cổ 2x2 cotton',
            'Bo cổ 1x1 rib',
            'Bo tay 1x1',
            'Bo gấu 2x2',
            'Bo cổ henley',
        ],
        ['Đen', 'Trắng', 'Navy', 'Xám melange', 'Xanh navy'],
        ['Cuộn 25kg', 'Cuộn 20kg', 'Cuộn 15kg'],
    ),
    (
        'day-khoa', 'cai',
        [
            'Dây kéo YKK #3',
            'Dây kéo YKK #5',
            'Dây kéo nhựa #5',
            'Dây rút polyester',
            'Nút nhựa 2 lỗ',
            'Nút nhựa 4 lỗ',
            'Khoen đồng',
            'Khuy cúc sơn',
        ],
        ['Đen', 'Trắng', 'Navy', 'Xám', 'Vàng đồng'],
        ['Dài 15cm', 'Dài 20cm', 'Dài 50cm', 'Ø 12mm', 'Ø 15mm', 'Ø 18mm'],
    ),
    (
        'tem-nhan', 'cai',
        [
            'Tem giấy size',
            'Tag treo thương hiệu JP',
            'Nhãn mã vạch EAN',
            'Tem giặt wash care',
            'Sticker size áo',
        ],
        ['Trắng', 'Đen', 'Kraft'],
        ['Size S/M/L/XL', 'Bộ 500 cái', 'Cuộn 1000 tem'],
    ),
    (
        'bao-bi', 'cai',
        [
            'Túi OPP đóng áo',
            'Túi PE trong suốt',
            'Thùng carton 5 lớp',
            'Giấy gói chống ẩm',
            'Băng keo đóng thùng',
        ],
        ['Trong', 'Trắng mờ', 'Nâu carton'],
        ['30x40cm', '35x45cm', '60x40x40cm', '50x35x30cm'],
    ),
    (
        'decal', 'cai',
        [
            'Decal heat transfer logo JP',
            'Decal số áo',
            'Decal reflective',
            'Decal tên CLB',
        ],
        ['Đen', 'Trắng', 'Bạc', 'Vàng'],
        ['8cm', '10cm', '12cm', 'A4 sheet'],
    ),
    (
        'chi-may', 'cuon',
        [
            'Chỉ polyester 40/2',
            'Chỉ polyester 60/3',
            'Chỉ cotton 50/3',
            'Chỉ overlock 80/2',
        ],
        ['Đen', 'Trắng', 'Navy', 'Đỏ', 'Xám'],
        ['Cuộn 3000m', 'Cuộn 5000m', 'Cuộn 10000m'],
    ),
    (
        'khac', 'goi',
        [
            'Keo dán tem nhiệt',
            'Giấy can cỡ áo',
            'Bút vẽ sơ đồ',
            'Kim máy DBx1',
            'Chun thun 1cm',
        ],
        ['—', 'Trắng', 'Đen'],
        ['Gói 100', 'Gói 500', 'Hộp 50'],
    ),
]

PRODUCT_CODES = [
    'JP-TSH-001', 'JP-TSH-002', 'JP-POLO-010', 'JP-HOD-020', 'JP-PAN-030',
    'JP-SWT-040', 'JP-JKT-050', 'JP-SHR-060', 'JP-KID-070', 'JP-ACC-080',
]

DEPARTMENTS = ['Xưởng may 1', 'Xưởng may 2', 'Xưởng cắt', 'Phòng R&D mẫu', 'Xưởng hoàn thiện']


class Command(BaseCommand):
    help = 'Tạo dữ liệu tồn kho NPL quy mô lớn (prefix PERF-) để test hiệu năng.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Xóa dữ liệu PERF- đã seed.')
        parser.add_argument('--materials', type=int, default=2000, help='Số NPL (mặc định 2000).')
        parser.add_argument('--receipts', type=int, default=500, help='Số phiếu nhập đã ghi sổ.')
        parser.add_argument('--issues', type=int, default=1500, help='Số phiếu xuất đã ghi sổ.')
        parser.add_argument('--adjustments', type=int, default=100, help='Số phiếu điều chỉnh.')
        parser.add_argument('--stocktakes', type=int, default=6, help='Số kỳ kiểm kê (5 chốt + 1 đang kiểm).')
        parser.add_argument('--user', default='Ductn', help='Username người tạo chứng từ.')
        parser.add_argument('--seed', type=int, default=42, help='Random seed tái lập.')

    def handle(self, *args, **options):
        if options['clear']:
            self._clear_perf_data()
            return

        rng = random.Random(options['seed'])
        user = self._get_user(options['user'])
        material_count = max(100, options['materials'])
        receipt_count = max(50, options['receipts'])
        issue_count = max(50, options['issues'])
        adjust_count = max(0, options['adjustments'])
        stocktake_count = max(1, options['stocktakes'])

        self.stdout.write(self.style.MIGRATE_HEADING('==> Seed kho NPL (PERF)'))
        t0 = timezone.now()

        locations = self._ensure_locations()
        suppliers = self._ensure_suppliers()
        categories = {c.code: c for c in MaterialCategory.objects.filter(is_active=True)}
        units = {u.code: u for u in Unit.objects.filter(is_active=True)}
        if not categories or not units.get('met'):
            raise CommandError('Thiếu master data — chạy migrate kho_npl trước.')

        materials = self._create_materials(
            rng, material_count, categories, units, suppliers,
        )
        self.stdout.write(f'  Materials: {len(materials)}')

        posted_receipts = self._create_receipts(
            rng, user, materials, locations, suppliers, receipt_count,
        )
        self.stdout.write(f'  Receipts posted: {posted_receipts}')

        posted_issues = self._create_issues(
            rng, user, materials, locations, issue_count,
        )
        self.stdout.write(f'  Issues posted: {posted_issues}')

        adj_stats = self._create_adjustments(rng, user, materials, locations, adjust_count)
        self.stdout.write(
            f'  Adjustments: {adj_stats["total"]} '
            f'(approved {adj_stats["approved"]}, pending {adj_stats["pending"]}, rejected {adj_stats["rejected"]})',
        )

        st_closed = self._create_stocktakes(rng, user, stocktake_count)
        self.stdout.write(f'  Stocktakes closed: {st_closed} (+1 counting if configured)')

        elapsed = (timezone.now() - t0).total_seconds()
        self._print_summary(elapsed)

    def _get_user(self, username: str):
        User = get_user_model()
        for candidate in (
            User.objects.filter(username=username).first(),
            User.objects.filter(username='admin').first(),
            User.objects.filter(is_superuser=True).order_by('id').first(),
            User.objects.filter(is_staff=True).order_by('id').first(),
        ):
            if candidate:
                return candidate
        raise CommandError(f'Khong tim thay user "{username}" (hoac admin/superuser).')

    def _ensure_locations(self) -> list[WarehouseLocation]:
        locations = list(WarehouseLocation.objects.filter(is_active=True))
        existing = {loc.code for loc in locations}
        for code, name in EXTRA_LOCATIONS:
            if code not in existing:
                locations.append(WarehouseLocation.objects.create(
                    code=code, name=name, is_active=True,
                ))
        return list(WarehouseLocation.objects.filter(is_active=True))

    def _ensure_suppliers(self) -> list[Supplier]:
        existing = set(Supplier.objects.values_list('code', flat=True))
        for code, name, phone in SUPPLIERS:
            if code in existing:
                continue
            Supplier.objects.create(code=code, name=name, phone=phone, is_active=True)
            existing.add(code)
        return list(Supplier.objects.filter(is_active=True))

    def _create_materials(self, rng, count, categories, units, suppliers) -> list[Material]:
        existing = Material.objects.filter(code__startswith=MATERIAL_PREFIX).count()
        if existing >= count:
            return list(Material.objects.filter(code__startswith=MATERIAL_PREFIX).order_by('code')[:count])

        blueprints = MATERIAL_BLUEPRINTS
        to_create = count - existing
        batch: list[Material] = []
        seq = existing + 1
        created: list[Material] = []

        for _ in range(to_create):
            cat_code, unit_code, templates, colors, specs = rng.choice(blueprints)
            category = categories.get(cat_code) or next(iter(categories.values()))
            unit = units.get(unit_code) or units['met']
            template = rng.choice(templates)
            color = rng.choice(colors)
            spec = rng.choice(specs)
            gsm = rng.choice([160, 180, 200, 220, 240, 280, 300])
            name = template.format(gsm=gsm) if '{gsm}' in template else template
            name = f'{name} — {color}'
            supplier = rng.choice(suppliers) if suppliers else None
            min_stock = Decimal(str(rng.choice([5, 10, 20, 50, 100, 200])))

            batch.append(Material(
                code=f'{MATERIAL_PREFIX}{seq:05d}',
                name=name,
                category=category,
                color=color,
                specification=spec,
                unit=unit,
                supplier=supplier,
                min_stock=min_stock,
                notes=f'Dữ liệu test hiệu năng ({PERF_TAG})',
                is_active=True,
            ))
            seq += 1

            if len(batch) >= 400:
                Material.objects.bulk_create(batch, ignore_conflicts=True)
                created.extend(batch)
                batch = []

        if batch:
            Material.objects.bulk_create(batch, ignore_conflicts=True)
            created.extend(batch)

        return list(Material.objects.filter(code__startswith=MATERIAL_PREFIX).order_by('code')[:count])

    def _random_past_date(self, rng, days_back: int = 180) -> date:
        offset = rng.randint(0, days_back)
        return timezone.localdate() - timedelta(days=offset)

    def _doc_number(self, prefix: str, seq: int) -> str:
        year = timezone.localdate().year
        return f'{prefix}-{PERF_TAG}-{year}-{seq:05d}'

    def _create_receipts(self, rng, user, materials, locations, suppliers, count) -> int:
        existing = StockReceipt.objects.filter(number__contains=f'-{PERF_TAG}-').count()
        to_create = max(0, count - existing)
        if not to_create:
            return 0
        start_seq = existing + 1
        lines_per_receipt = 4
        material_pool = materials[:]
        rng.shuffle(material_pool)
        idx = 0
        posted = 0

        for i in range(to_create):
            seq = start_seq + i
            number = self._doc_number('PN', seq)
            if StockReceipt.objects.filter(number=number).exists():
                continue

            receipt = StockReceipt.objects.create(
                number=number,
                receipt_date=self._random_past_date(rng, 200),
                supplier=rng.choice(suppliers),
                po_number=f'PO-{PERF_TAG}-{seq:05d}',
                received_by=user,
                checked_by=user,
                created_by=user,
                notes=f'Nhập kho đầu kỳ / bổ sung ({PERF_TAG})',
            )
            line_objs = []
            for _ in range(lines_per_receipt):
                material = material_pool[idx % len(material_pool)]
                idx += 1
                location = rng.choice(locations)
                qty = Decimal(str(rng.randint(50, 800)))
                if material.unit.code in ('cuon', 'goi'):
                    qty = Decimal(str(rng.randint(5, 80)))
                elif material.unit.code == 'cai':
                    qty = Decimal(str(rng.randint(100, 5000)))
                line_objs.append(StockReceiptLine(
                    receipt=receipt,
                    material=material,
                    ordered_qty=qty,
                    received_qty=qty,
                    location=location,
                ))
            StockReceiptLine.objects.bulk_create(line_objs)
            post_stock_receipt(receipt, user)
            posted += 1
            if posted % 100 == 0:
                self.stdout.write(f'    ... receipts {posted}/{to_create}')

        return posted

    def _balances_with_stock(self, min_qty=Decimal('10')):
        return list(
            StockBalance.objects.filter(quantity__gte=min_qty)
            .select_related('material', 'location')
            .order_by('?')[:5000]
        )

    def _create_issues(self, rng, user, materials, locations, count) -> int:
        existing = StockIssue.objects.filter(number__contains=f'-{PERF_TAG}-').count()
        to_create = max(0, count - existing)
        if not to_create:
            return 0
        start_seq = existing + 1
        issue_types = [c[0] for c in ISSUE_TYPE_CHOICES]
        weights = [50, 10, 8, 5, 12, 15]
        posted = 0

        for i in range(to_create):
            balances = self._balances_with_stock(Decimal('5'))
            if not balances:
                break

            seq = start_seq + i
            number = self._doc_number('PX', seq)
            if StockIssue.objects.filter(number=number).exists():
                continue

            issue_type = rng.choices(issue_types, weights=weights, k=1)[0]
            issue = StockIssue.objects.create(
                number=number,
                issue_date=self._random_past_date(rng, 150),
                issue_type=issue_type,
                production_order=f'LSX-{PERF_TAG}-{rng.randint(1000, 9999)}' if issue_type == ISSUE_TYPE_PRODUCTION else '',
                product_code=rng.choice(PRODUCT_CODES) if issue_type == ISSUE_TYPE_PRODUCTION else '',
                recipient_department=rng.choice(DEPARTMENTS),
                recipient_name=f'NV-{rng.randint(100, 999)}',
                issued_by=user,
                created_by=user,
                notes=f'Xuất kho sản xuất / mẫu ({PERF_TAG})',
            )

            line_count = rng.randint(1, 3)
            picked = rng.sample(balances, min(line_count, len(balances)))
            line_objs = []
            for bal in picked:
                max_issue = bal.quantity * Decimal('0.4')
                if max_issue < Decimal('1'):
                    max_issue = bal.quantity
                qty = Decimal(str(rng.randint(1, int(max(max_issue, Decimal('1'))))))
                if qty > bal.quantity:
                    qty = bal.quantity
                if qty < Decimal('0.001'):
                    continue
                line_objs.append(StockIssueLine(
                    issue=issue,
                    material=bal.material,
                    quantity=qty,
                    location=bal.location,
                ))
            if not line_objs:
                issue.delete()
                continue
            StockIssueLine.objects.bulk_create(line_objs)
            try:
                post_stock_issue(issue, user)
            except Exception:
                issue.delete()
                continue
            posted += 1
            if posted % 200 == 0:
                self.stdout.write(f'    ... issues {posted}/{to_create}')

        return posted

    def _create_adjustments(self, rng, user, materials, locations, count) -> dict:
        existing = StockAdjustment.objects.filter(number__contains=f'-{PERF_TAG}-').count()
        to_create = max(0, count - existing)
        start_seq = existing + 1
        stats = {'total': 0, 'approved': 0, 'pending': 0, 'rejected': 0}

        for i in range(to_create):
            material = rng.choice(materials)
            location = rng.choice(locations)
            balance = StockBalance.objects.filter(material=material, location=location).first()
            system_qty = balance.quantity if balance else Decimal('0')
            if system_qty <= 0 and rng.random() < 0.7:
                continue

            seq = start_seq + stats['total']
            number = self._doc_number('DC', seq)
            if StockAdjustment.objects.filter(number=number).exists():
                continue

            delta = Decimal(str(rng.randint(-20, 20)))
            actual_qty = max(Decimal('0'), system_qty + delta)
            adj = StockAdjustment.objects.create(
                number=number,
                adjust_date=self._random_past_date(rng, 90),
                reason=f'Điều chỉnh sau kiểm kê / sai lệch nhập ({PERF_TAG})',
                proposed_by=user,
            )
            StockAdjustmentLine.objects.create(
                adjustment=adj,
                material=material,
                location=location,
                system_qty=system_qty,
                actual_qty=actual_qty,
            )
            stats['total'] += 1
            roll = rng.random()
            if roll < 0.75:
                approve_stock_adjustment(adj, user)
                stats['approved'] += 1
            elif roll < 0.9:
                stats['pending'] += 1
            else:
                reject_stock_adjustment(adj, user)
                stats['rejected'] += 1

        return stats

    def _create_stocktakes(self, rng, user, count) -> int:
        existing = Stocktake.objects.filter(number__contains=f'-{PERF_TAG}-').count()
        to_create = max(0, count - existing)
        start_seq = existing + 1
        closed = 0
        close_target = max(1, to_create - 1) if to_create else 0

        for i in range(to_create):
            seq = start_seq + i
            number = self._doc_number('KK', seq)
            if Stocktake.objects.filter(number=number).exists():
                continue

            st = Stocktake.objects.create(
                number=number,
                name=f'Kiểm kê định kỳ {PERF_TAG} — đợt {seq}',
                stocktake_date=self._random_past_date(rng, 120),
                created_by=user,
                notes=f'Kiểm kê test hiệu năng ({PERF_TAG})',
            )
            start_stocktake_counting(st)

            if i < close_target:
                for line in st.lines.all():
                    variance = Decimal(str(rng.randint(-3, 3)))
                    line.actual_qty = max(Decimal('0'), line.system_qty + variance)
                    line.save(update_fields=['actual_qty'])
                close_stocktake(st, user)
                closed += 1
            else:
                sample = list(st.lines.all()[: min(200, st.lines.count())])
                for line in sample:
                    line.actual_qty = line.system_qty
                    line.save(update_fields=['actual_qty'])

        return closed

    def _print_summary(self, elapsed: float):
        mats = Material.objects.filter(code__startswith=MATERIAL_PREFIX).count()
        balances = StockBalance.objects.filter(material__code__startswith=MATERIAL_PREFIX).count()
        ledger = StockLedger.objects.filter(material__code__startswith=MATERIAL_PREFIX).count()
        receipts = StockReceipt.objects.filter(number__contains=f'-{PERF_TAG}-').count()
        issues = StockIssue.objects.filter(number__contains=f'-{PERF_TAG}-').count()

        self.stdout.write(self.style.SUCCESS('\n==> Seed kho NPL done'))
        self.stdout.write(f'  Materials (PERF): {mats:,}')
        self.stdout.write(f'  Stock balances:   {balances:,}')
        self.stdout.write(f'  Ledger rows:      {ledger:,}')
        self.stdout.write(f'  Receipts:         {receipts:,}')
        self.stdout.write(f'  Issues:           {issues:,}')
        self.stdout.write(f'  Elapsed:          {elapsed:.1f}s')
        self.stdout.write(self.style.WARNING(
            '\nClear test data: python manage.py seed_kho_npl_perf --clear',
        ))

    @transaction.atomic
    def _clear_perf_data(self):
        self.stdout.write(self.style.WARNING('==> Clearing PERF kho NPL data...'))

        transfer_ids = list(
            StockTransfer.objects.filter(notes=SEED_TRANSFER_NOTE).values_list('pk', flat=True),
        )
        if transfer_ids:
            StockLedger.objects.filter(
                ref_type=StockLedger.REF_TRANSFER,
                ref_id__in=transfer_ids,
            ).delete()
            deleted, _ = StockTransfer.objects.filter(pk__in=transfer_ids).delete()
            self.stdout.write(f'  Deleted {deleted} seed transfer(s).')

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
            self.stdout.write(f'  Deleted {deleted} seed opening receipt(s).')

        perf_materials = Material.objects.filter(code__startswith=MATERIAL_PREFIX)
        perf_ids = list(perf_materials.values_list('pk', flat=True))

        StockLedger.objects.filter(material_id__in=perf_ids).delete()
        StocktakeLine.objects.filter(material_id__in=perf_ids).delete()
        StockAdjustment.objects.filter(lines__material_id__in=perf_ids).delete()
        StockIssueLine.objects.filter(material_id__in=perf_ids).delete()
        StockReceiptLine.objects.filter(material_id__in=perf_ids).delete()
        StockBalance.objects.filter(material_id__in=perf_ids).delete()

        Stocktake.objects.filter(number__contains=f'-{PERF_TAG}-').delete()
        StockIssue.objects.filter(number__contains=f'-{PERF_TAG}-').delete()
        StockReceipt.objects.filter(number__contains=f'-{PERF_TAG}-').delete()
        StockAdjustment.objects.filter(number__contains=f'-{PERF_TAG}-').delete()

        deleted_mats, _ = perf_materials.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {deleted_mats} materials and related docs (prefix {MATERIAL_PREFIX}).',
        ))
