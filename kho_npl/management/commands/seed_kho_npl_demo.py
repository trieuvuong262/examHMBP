"""
Tạo dữ liệu demo kho NPL — ngành may quần áo thể thao JustPlay.

Usage:
    python manage.py seed_kho_npl_demo
    python manage.py seed_kho_npl_demo --clear
    python manage.py seed_kho_npl_demo --user admin
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from kho_npl.choices import (
    DEFAULT_MATERIAL_CATEGORIES,
    DISPOSAL_REASON_DAMAGED,
    ISSUE_TYPE_PRODUCTION,
    ISSUE_TYPE_SAMPLE,
    ISSUE_TYPE_WASTE,
    TRANSFER_STATUS_DRAFT,
    TRANSFER_STATUS_IN_TRANSIT,
    TRANSFER_STATUS_RECEIVED,
    WAREHOUSE_SCRAP_CODE,
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
from kho_npl.services.stocktakes import close_stocktake, start_stocktake_counting
from kho_npl.services.transfers import receive_stock_transfer, send_stock_transfer

DEMO_TAG = 'DEMO'
MATERIAL_PREFIX = 'JP-'
DEMO_NOTE = f'Dữ liệu demo kho NPL ({DEMO_TAG}) — quần áo thể thao JustPlay'

LOCATIONS = [
    ('KE-A1', 'Kệ A1 — Vải chính'),
    ('KE-A2', 'Kệ A2 — Vải phối / bo'),
    ('KE-B1', 'Kệ B1 — Phụ liệu may'),
    ('KE-B2', 'Kệ B2 — Tem / bao bì / decal'),
    ('XUONG-SX', 'Kho xưởng sản xuất'),
    ('KHO-PL', 'Kho phụ liệu lẻ'),
]

SUPPLIERS = [
    ('NCC-VAI-DN', 'Công ty TNHH Vải Đồng Nai', '0903123456'),
    ('NCC-VAI-HCM', 'Vải Thành Công — TP.HCM', '02838234567'),
    ('NCC-PHULIEU-BD', 'Phụ liệu May Bình Dương', '02743891234'),
    ('NCC-YKK-VN', 'YKK Việt Nam — Dây kéo', '02837778899'),
    ('NCC-TEM-HN', 'In Tem Hà Nội', '02435678901'),
    ('NCC-BAOBI-TG', 'Bao bì Tiền Giang', '02733881234'),
    ('NCC-CHI-POLY', 'Chỉ Polyester Đại Phát', '0908765432'),
    ('NCC-DECAL-SG', 'Decal Heat Transfer Sài Gòn', '0909111222'),
]

# code, name, category, unit, color, spec, supplier_code, min_stock
DEMO_MATERIALS = [
    ('VAI-COT180-WHT', 'Vải cotton 100% 180gsm — Trắng', 'vai-chinh', 'met', 'Trắng', 'Khổ 1m6', 'NCC-VAI-DN', 200),
    ('VAI-COT180-BLK', 'Vải cotton 100% 180gsm — Đen', 'vai-chinh', 'met', 'Đen', 'Khổ 1m6', 'NCC-VAI-DN', 200),
    ('VAI-COT180-NVY', 'Vải cotton 100% 180gsm — Navy', 'vai-chinh', 'met', 'Navy', 'Khổ 1m6', 'NCC-VAI-HCM', 150),
    ('VAI-PES4W-220-GRY', 'Vải polyester spandex 4 chiều 220gsm — Xám melange', 'vai-chinh', 'met', 'Xám melange', 'Khổ 1m7', 'NCC-VAI-HCM', 180),
    ('VAI-PES4W-220-BLK', 'Vải polyester spandex 4 chiều 220gsm — Đen', 'vai-chinh', 'met', 'Đen', 'Khổ 1m7', 'NCC-VAI-HCM', 180),
    ('VAI-FRT-280-NVY', 'Vải French Terry 280gsm — Navy (hoodie)', 'vai-chinh', 'met', 'Navy', 'Khổ 1m8', 'NCC-VAI-DN', 120),
    ('VAI-FRT-280-GRY', 'Vải French Terry 280gsm — Xám melange', 'vai-chinh', 'met', 'Xám melange', 'Khổ 1m8', 'NCC-VAI-DN', 100),
    ('VAI-PIQ-200-WHT', 'Vải pique cotton 200gsm — Trắng (polo)', 'vai-chinh', 'met', 'Trắng', 'Khổ 1m6', 'NCC-VAI-HCM', 80),
    ('VAI-MES-150-BLK', 'Vải mesh polyester thoáng — Đen (áo training)', 'vai-chinh', 'met', 'Đen', 'Khổ 1m5', 'NCC-VAI-HCM', 60),
    ('VAI-INT-200-RED', 'Vải interlock cotton 200gsm — Đỏ đô (đội tuyển)', 'vai-chinh', 'met', 'Đỏ đô', 'Khổ 1m6', 'NCC-VAI-DN', 90),
    ('VAI-RIB-1X1-WHT', 'Vải rib 1x1 cổ áo — Trắng', 'vai-phoi', 'met', 'Trắng', 'Khổ 40cm', 'NCC-VAI-DN', 40),
    ('VAI-RIB-1X1-NVY', 'Vải rib 1x1 cổ áo — Navy', 'vai-phoi', 'met', 'Navy', 'Khổ 40cm', 'NCC-VAI-DN', 40),
    ('VAI-RIB-2X2-BLK', 'Vải rib 2x2 bo tay — Đen', 'vai-phoi', 'met', 'Đen', 'Khổ 30cm', 'NCC-VAI-DN', 30),
    ('VAI-LOT-PES-WHT', 'Vải lót polyester — Trắng', 'vai-phoi', 'met', 'Trắng', 'Khổ 1m5', 'NCC-VAI-HCM', 50),
    ('BO-CO-2X2-BLK', 'Bo cổ 2x2 cotton — Đen', 'bo-co-tay', 'cuon', 'Đen', 'Cuộn 25kg', 'NCC-PHULIEU-BD', 5),
    ('BO-CO-2X2-WHT', 'Bo cổ 2x2 cotton — Trắng', 'bo-co-tay', 'cuon', 'Trắng', 'Cuộn 25kg', 'NCC-PHULIEU-BD', 5),
    ('BO-TAY-1X1-NVY', 'Bo tay 1x1 — Navy', 'bo-co-tay', 'cuon', 'Navy', 'Cuộn 20kg', 'NCC-PHULIEU-BD', 4),
    ('BO-GAU-2X2-GRY', 'Bo gấu 2x2 — Xám melange', 'bo-co-tay', 'cuon', 'Xám melange', 'Cuộn 15kg', 'NCC-PHULIEU-BD', 3),
    ('DZ-YKK3-15-BLK', 'Dây kéo YKK #3 — 15cm Đen', 'day-khoa', 'cai', 'Đen', 'Dài 15cm', 'NCC-YKK-VN', 500),
    ('DZ-YKK3-15-WHT', 'Dây kéo YKK #3 — 15cm Trắng', 'day-khoa', 'cai', 'Trắng', 'Dài 15cm', 'NCC-YKK-VN', 500),
    ('DZ-YKK5-20-NVY', 'Dây kéo YKK #5 — 20cm Navy (hoodie)', 'day-khoa', 'cai', 'Navy', 'Dài 20cm', 'NCC-YKK-VN', 300),
    ('DZ-RUT-PES-BLK', 'Dây rút polyester — Đen (quần jogger)', 'day-khoa', 'cai', 'Đen', 'Dài 50cm', 'NCC-PHULIEU-BD', 400),
    ('NUT-2L-12-BLK', 'Nút nhựa 2 lỗ — Ø12mm Đen', 'day-khoa', 'cai', 'Đen', 'Ø 12mm', 'NCC-PHULIEU-BD', 2000),
    ('NUT-4L-15-WHT', 'Nút nhựa 4 lỗ — Ø15mm Trắng (polo)', 'day-khoa', 'cai', 'Trắng', 'Ø 15mm', 'NCC-PHULIEU-BD', 1500),
    ('CHI-PES40-BLK', 'Chỉ polyester 40/2 — Đen', 'chi-may', 'cuon', 'Đen', 'Cuộn 5000m', 'NCC-CHI-POLY', 10),
    ('CHI-PES40-WHT', 'Chỉ polyester 40/2 — Trắng', 'chi-may', 'cuon', 'Trắng', 'Cuộn 5000m', 'NCC-CHI-POLY', 10),
    ('CHI-PES60-NVY', 'Chỉ polyester 60/3 — Navy (may đế)', 'chi-may', 'cuon', 'Navy', 'Cuộn 3000m', 'NCC-CHI-POLY', 8),
    ('CHI-OVL-80-GRY', 'Chỉ overlock 80/2 — Xám', 'chi-may', 'cuon', 'Xám', 'Cuộn 10000m', 'NCC-CHI-POLY', 6),
    ('TEM-SIZE-JP', 'Tem giấy size S/M/L/XL — JustPlay', 'tem-nhan', 'cai', 'Trắng', 'Bộ 500 cái', 'NCC-TEM-HN', 3000),
    ('TAG-HANG-JP', 'Tag treo thương hiệu JustPlay', 'tem-nhan', 'cai', 'Kraft', 'Cuộn 1000 tem', 'NCC-TEM-HN', 2000),
    ('NHAN-GIAT-VN', 'Tem giặt wash care — tiếng Việt', 'tem-nhan', 'cai', 'Trắng', 'Bộ 500 cái', 'NCC-TEM-HN', 2500),
    ('STICK-SIZE-CLR', 'Sticker size áo — trong suốt', 'tem-nhan', 'cai', 'Trong', 'Cuộn 2000 tem', 'NCC-TEM-HN', 1500),
    ('TUI-OPP-30x40', 'Túi OPP đóng áo — 30×40cm', 'bao-bi', 'cai', 'Trong', '30×40cm', 'NCC-BAOBI-TG', 5000),
    ('TUI-PE-35x45', 'Túi PE trong suốt — 35×45cm', 'bao-bi', 'cai', 'Trong', '35×45cm', 'NCC-BAOBI-TG', 4000),
    ('THUNG-CTN-5L', 'Thùng carton 5 lớp — đóng hàng xuất', 'bao-bi', 'cai', 'Nâu carton', '60×40×40cm', 'NCC-BAOBI-TG', 200),
    ('GIAY-GOI-50', 'Giấy gói chống ẩm — cuộn 50m', 'bao-bi', 'cuon', 'Trắng mờ', 'Khổ 1m', 'NCC-BAOBI-TG', 5),
    ('DEC-LOGO-JP-8', 'Decal heat transfer logo JP — 8cm', 'decal', 'cai', 'Đen', '8cm', 'NCC-DECAL-SG', 800),
    ('DEC-LOGO-JP-10', 'Decal heat transfer logo JP — 10cm (hoodie)', 'decal', 'cai', 'Trắng', '10cm', 'NCC-DECAL-SG', 600),
    ('DEC-SO-AO-10', 'Decal số áo — 10cm reflective', 'decal', 'cai', 'Bạc', '10cm', 'NCC-DECAL-SG', 400),
    ('DEC-TEN-CLB-12', 'Decal tên CLB — 12cm', 'decal', 'cai', 'Vàng', '12cm', 'NCC-DECAL-SG', 300),
    ('KEO-TEM-100', 'Keo dán tem nhiệt', 'khac', 'goi', '—', 'Gói 100', 'NCC-PHULIEU-BD', 20),
    ('CHUN-1CM-WHT', 'Chun thun 1cm — Trắng (quần short)', 'khac', 'cuon', 'Trắng', 'Cuộn 100m', 'NCC-PHULIEU-BD', 8),
    ('KIM-DBX1-90', 'Kim máy DB×1 — bộ 90 kim', 'khac', 'goi', '—', 'Hộp 50', 'NCC-PHULIEU-BD', 15),
    ('GIAY-CAN-A4', 'Giấy can cỡ áo — A4', 'khac', 'goi', 'Trắng', 'Gói 500', 'NCC-PHULIEU-BD', 10),
    ('VAI-COT180-BEG', 'Vải cotton 180gsm — Be (bộ đồ yoga)', 'vai-chinh', 'met', 'Be', 'Khổ 1m6', 'NCC-VAI-DN', 70),
    ('VAI-PES4W-180-PNK', 'Vải polyester spandex — Hồng pastel (nữ)', 'vai-chinh', 'met', 'Hồng pastel', 'Khổ 1m5', 'NCC-VAI-HCM', 50),
    ('VAI-FLEECE-GRN', 'Vải fleece nỉ bông — Xanh rêu (áo khoác)', 'vai-chinh', 'met', 'Xanh rêu', 'Khổ 1m7', 'NCC-VAI-DN', 40),
]

# receipt_number, date_offset_days, supplier_code, po, lines: (material_code, qty, location_code)
DEMO_RECEIPTS = [
    (
        f'PN-{DEMO_TAG}-2026-001', 45, 'NCC-VAI-DN', 'PO-JP-VAI-2401',
        [
            ('VAI-COT180-WHT', 850, 'KE-A1'),
            ('VAI-COT180-BLK', 920, 'KE-A1'),
            ('VAI-COT180-NVY', 640, 'KE-A1'),
            ('VAI-FRT-280-NVY', 380, 'KE-A1'),
            ('VAI-FRT-280-GRY', 290, 'KE-A1'),
        ],
    ),
    (
        f'PN-{DEMO_TAG}-2026-002', 40, 'NCC-VAI-HCM', 'PO-JP-VAI-2402',
        [
            ('VAI-PES4W-220-GRY', 720, 'KE-A1'),
            ('VAI-PES4W-220-BLK', 680, 'KE-A1'),
            ('VAI-PIQ-200-WHT', 310, 'KE-A1'),
            ('VAI-MES-150-BLK', 220, 'KE-A1'),
            ('VAI-INT-200-RED', 180, 'KE-A1'),
            ('VAI-COT180-BEG', 150, 'KE-A1'),
            ('VAI-PES4W-180-PNK', 120, 'KE-A1'),
            ('VAI-FLEECE-GRN', 95, 'KE-A1'),
        ],
    ),
    (
        f'PN-{DEMO_TAG}-2026-003', 35, 'NCC-VAI-DN', 'PO-JP-PHOI-2403',
        [
            ('VAI-RIB-1X1-WHT', 120, 'KE-A2'),
            ('VAI-RIB-1X1-NVY', 110, 'KE-A2'),
            ('VAI-RIB-2X2-BLK', 85, 'KE-A2'),
            ('VAI-LOT-PES-WHT', 95, 'KE-A2'),
            ('BO-CO-2X2-BLK', 12, 'KE-A2'),
            ('BO-CO-2X2-WHT', 10, 'KE-A2'),
            ('BO-TAY-1X1-NVY', 8, 'KE-A2'),
            ('BO-GAU-2X2-GRY', 6, 'KE-A2'),
        ],
    ),
    (
        f'PN-{DEMO_TAG}-2026-004', 30, 'NCC-PHULIEU-BD', 'PO-JP-PL-2404',
        [
            ('DZ-YKK3-15-BLK', 3500, 'KE-B1'),
            ('DZ-YKK3-15-WHT', 2800, 'KE-B1'),
            ('DZ-YKK5-20-NVY', 1200, 'KE-B1'),
            ('DZ-RUT-PES-BLK', 2200, 'KE-B1'),
            ('NUT-2L-12-BLK', 12000, 'KE-B1'),
            ('NUT-4L-15-WHT', 8000, 'KE-B1'),
            ('CHI-PES40-BLK', 18, 'KE-B1'),
            ('CHI-PES40-WHT', 16, 'KE-B1'),
            ('CHI-PES60-NVY', 12, 'KE-B1'),
            ('CHI-OVL-80-GRY', 8, 'KE-B1'),
            ('KEO-TEM-100', 25, 'KE-B1'),
            ('CHUN-1CM-WHT', 12, 'KE-B1'),
            ('KIM-DBX1-90', 20, 'KE-B1'),
            ('GIAY-CAN-A4', 15, 'KE-B1'),
        ],
    ),
    (
        f'PN-{DEMO_TAG}-2026-005', 25, 'NCC-TEM-HN', 'PO-JP-TEM-2405',
        [
            ('TEM-SIZE-JP', 15000, 'KE-B2'),
            ('TAG-HANG-JP', 10000, 'KE-B2'),
            ('NHAN-GIAT-VN', 12000, 'KE-B2'),
            ('STICK-SIZE-CLR', 8000, 'KE-B2'),
            ('TUI-OPP-30x40', 25000, 'KE-B2'),
            ('TUI-PE-35x45', 18000, 'KE-B2'),
            ('THUNG-CTN-5L', 800, 'KE-B2'),
            ('GIAY-GOI-50', 12, 'KE-B2'),
            ('DEC-LOGO-JP-8', 2500, 'KE-B2'),
            ('DEC-LOGO-JP-10', 1800, 'KE-B2'),
            ('DEC-SO-AO-10', 1200, 'KE-B2'),
            ('DEC-TEN-CLB-12', 900, 'KE-B2'),
        ],
    ),
]

DEMO_ISSUES = [
    (
        f'PX-{DEMO_TAG}-2026-001', 20, ISSUE_TYPE_PRODUCTION, 'LSX-JP-2601', 'JP-TSH-001',
        'Xưởng may 1', 'Nguyễn Văn Hùng',
        [
            ('VAI-COT180-WHT', 180, 'KE-A1'),
            ('VAI-RIB-1X1-WHT', 25, 'KE-A2'),
            ('DZ-YKK3-15-BLK', 420, 'KE-B1'),
            ('CHI-PES40-WHT', 2, 'KE-B1'),
            ('TEM-SIZE-JP', 500, 'KE-B2'),
            ('TAG-HANG-JP', 500, 'KE-B2'),
        ],
    ),
    (
        f'PX-{DEMO_TAG}-2026-002', 18, ISSUE_TYPE_PRODUCTION, 'LSX-JP-2602', 'JP-HOD-020',
        'Xưởng may 2', 'Trần Thị Lan',
        [
            ('VAI-FRT-280-NVY', 95, 'KE-A1'),
            ('VAI-FRT-280-GRY', 40, 'KE-A1'),
            ('DZ-YKK5-20-NVY', 180, 'KE-B1'),
            ('DEC-LOGO-JP-10', 200, 'KE-B2'),
            ('CHI-PES60-NVY', 1, 'KE-B1'),
        ],
    ),
    (
        f'PX-{DEMO_TAG}-2026-003', 15, ISSUE_TYPE_PRODUCTION, 'LSX-JP-2603', 'JP-PAN-030',
        'Xưởng may 1', 'Lê Minh Tuấn',
        [
            ('VAI-PES4W-220-BLK', 120, 'KE-A1'),
            ('DZ-RUT-PES-BLK', 350, 'KE-B1'),
            ('CHUN-1CM-WHT', 3, 'KE-B1'),
            ('CHI-PES40-BLK', 2, 'KE-B1'),
        ],
    ),
    (
        f'PX-{DEMO_TAG}-2026-004', 12, ISSUE_TYPE_SAMPLE, '', 'JP-POLO-010',
        'Phòng R&D mẫu', 'Phạm Thu Hà',
        [
            ('VAI-PIQ-200-WHT', 8, 'KE-A1'),
            ('NUT-4L-15-WHT', 30, 'KE-B1'),
            ('DEC-LOGO-JP-8', 15, 'KE-B2'),
        ],
    ),
    (
        f'PX-{DEMO_TAG}-2026-005', 10, ISSUE_TYPE_PRODUCTION, 'LSX-JP-2604', 'JP-JER-040',
        'Xưởng may 2', 'Hoàng Quốc Bảo',
        [
            ('VAI-INT-200-RED', 65, 'KE-A1'),
            ('DEC-SO-AO-10', 150, 'KE-B2'),
            ('DEC-TEN-CLB-12', 80, 'KE-B2'),
            ('TUI-OPP-30x40', 600, 'KE-B2'),
        ],
    ),
    (
        f'PX-{DEMO_TAG}-2026-006', 8, ISSUE_TYPE_WASTE, '', '',
        'Xưởng cắt', 'Võ Đức Anh',
        [
            ('VAI-COT180-BLK', 12, 'KE-A1'),
            ('VAI-RIB-2X2-BLK', 3, 'KE-A2'),
        ],
    ),
    (
        f'PX-{DEMO_TAG}-2026-007', 5, ISSUE_TYPE_PRODUCTION, 'LSX-JP-2605', 'JP-SHR-060',
        'Xưởng may 1', 'Đặng Thị Mai',
        [
            ('VAI-MES-150-BLK', 45, 'KE-A1'),
            ('CHI-OVL-80-GRY', 1, 'KE-B1'),
            ('NHAN-GIAT-VN', 300, 'KE-B2'),
        ],
    ),
]


class Command(BaseCommand):
    help = 'Tạo dữ liệu demo kho NPL — may quần áo thể thao JustPlay (prefix JP-).'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Xóa dữ liệu demo đã seed.')
        parser.add_argument('--user', default='', help='Username người tạo chứng từ (mặc định: admin/superuser).')

    def handle(self, *args, **options):
        if options['clear']:
            self._clear_demo_data()
            return

        if Material.objects.filter(code__startswith=MATERIAL_PREFIX).exists():
            self.stdout.write(self.style.WARNING(
                'Đã có NPL demo (prefix JP-). Dùng --clear để xóa rồi seed lại.',
            ))
            return

        user = self._get_user(options['user'])
        today = timezone.localdate()
        self.stdout.write(self.style.MIGRATE_HEADING('==> Seed kho NPL demo (the thao)'))

        locations = self._ensure_locations()
        suppliers = self._ensure_suppliers()
        categories, units = self._ensure_master_data()
        supplier_map = {s.code: s for s in suppliers}
        location_map = {loc.code: loc for loc in locations}

        if not categories or not units:
            raise CommandError('Thieu master data — chay migrate kho_npl truoc.')

        materials = self._create_materials(categories, units, supplier_map)
        self.stdout.write(f'  Materials: {len(materials)}')
        material_map = {row[0]: materials[i] for i, row in enumerate(DEMO_MATERIALS)}

        receipts = self._create_receipts(user, today, material_map, location_map, supplier_map)
        self.stdout.write(f'  Receipts posted: {receipts}')

        issues = self._create_issues(user, today, material_map, location_map)
        self.stdout.write(f'  Issues posted: {issues}')

        transfers = self._create_transfers(user, today, material_map, location_map)
        self.stdout.write(f'  Transfers: {transfers}')

        self._create_adjustments(user, today, material_map, location_map)
        self.stdout.write('  Adjustments: 2 (1 approved, 1 pending)')

        self._create_stocktake(user, today, location_map)
        self.stdout.write('  Stocktake: 1 counting')

        self._create_disposal(user, today, material_map, location_map)
        self.stdout.write('  Disposal: 1')

        self._print_summary()

    def _get_user(self, username: str):
        User = get_user_model()
        if username:
            user = User.objects.filter(username=username).first()
            if user:
                return user
            raise CommandError(f'Không tìm thấy user "{username}".')
        for candidate in (
            User.objects.filter(username='admin').first(),
            User.objects.filter(is_superuser=True).order_by('id').first(),
            User.objects.filter(is_staff=True).order_by('id').first(),
            User.objects.filter(is_active=True).order_by('id').first(),
        ):
            if candidate:
                return candidate
        raise CommandError('Không tìm thấy user — tạo user hoặc truyền --user.')

    def _ensure_master_data(self) -> tuple[dict, dict]:
        for code, name, sort_order in DEFAULT_MATERIAL_CATEGORIES:
            MaterialCategory.objects.get_or_create(
                code=code,
                defaults={'name': name, 'sort_order': sort_order, 'is_active': True},
            )
        for code, name in [
            ('met', 'Mét'),
            ('cuon', 'Cuộn'),
            ('cai', 'Cái'),
            ('bo', 'Bộ'),
            ('kg', 'Kg'),
            ('goi', 'Gói'),
        ]:
            Unit.objects.get_or_create(code=code, defaults={'name': name, 'is_active': True})
        WarehouseLocation.objects.get_or_create(
            code='MAIN',
            defaults={'name': 'Kho chính', 'is_active': True},
        )
        categories = {c.code: c for c in MaterialCategory.objects.filter(is_active=True)}
        units = {u.code: u for u in Unit.objects.filter(is_active=True)}
        return categories, units

    def _ensure_locations(self) -> list[WarehouseLocation]:
        locations = list(WarehouseLocation.objects.filter(is_active=True))
        existing = {loc.code for loc in locations}
        for code, name in LOCATIONS:
            if code not in existing:
                locations.append(WarehouseLocation.objects.create(
                    code=code, name=name, is_active=True,
                ))
        WarehouseLocation.objects.get_or_create(
            code=WAREHOUSE_SCRAP_CODE,
            defaults={'name': 'Kho hủy', 'is_active': True},
        )
        return list(WarehouseLocation.objects.filter(is_active=True))

    def _ensure_suppliers(self) -> list[Supplier]:
        existing = set(Supplier.objects.values_list('code', flat=True))
        for code, name, phone in SUPPLIERS:
            if code in existing:
                continue
            Supplier.objects.create(code=code, name=name, phone=phone, is_active=True)
            existing.add(code)
        return list(Supplier.objects.filter(is_active=True))

    def _create_materials(self, categories, units, supplier_map) -> list[Material]:
        created = []
        for code, name, cat_code, unit_code, color, spec, sup_code, min_stock in DEMO_MATERIALS:
            full_code = f'{MATERIAL_PREFIX}{code}'
            material = Material.objects.create(
                code=full_code,
                name=name,
                category=categories[cat_code],
                color=color,
                specification=spec,
                unit=units[unit_code],
                supplier=supplier_map.get(sup_code),
                min_stock=Decimal(str(min_stock)),
                notes=DEMO_NOTE,
                is_active=True,
            )
            created.append(material)
        return created

    def _create_receipts(self, user, today, material_map, location_map, supplier_map) -> int:
        posted = 0
        for number, days_ago, sup_code, po, lines in DEMO_RECEIPTS:
            if StockReceipt.objects.filter(number=number).exists():
                continue
            receipt = StockReceipt.objects.create(
                number=number,
                receipt_date=today - timedelta(days=days_ago),
                supplier=supplier_map.get(sup_code),
                po_number=po,
                received_by=user,
                checked_by=user,
                created_by=user,
                notes=f'Nhập vải & phụ liệu đầu mùa — {DEMO_NOTE}',
            )
            for mat_code, qty, loc_code in lines:
                StockReceiptLine.objects.create(
                    receipt=receipt,
                    material=material_map[mat_code],
                    ordered_qty=Decimal(str(qty)),
                    received_qty=Decimal(str(qty)),
                    location=location_map[loc_code],
                )
            post_stock_receipt(receipt, user)
            posted += 1
        return posted

    def _create_issues(self, user, today, material_map, location_map) -> int:
        posted = 0
        for (
            number, days_ago, issue_type, lsx, product, dept, recipient, lines,
        ) in DEMO_ISSUES:
            if StockIssue.objects.filter(number=number).exists():
                continue
            issue = StockIssue.objects.create(
                number=number,
                issue_date=today - timedelta(days=days_ago),
                issue_type=issue_type,
                production_order=lsx,
                product_code=product,
                recipient_department=dept,
                recipient_name=recipient,
                issued_by=user,
                created_by=user,
                notes=f'Xuất cho sản xuất / mẫu — {DEMO_NOTE}',
            )
            line_objs = []
            for mat_code, qty, loc_code in lines:
                line_objs.append(StockIssueLine(
                    issue=issue,
                    material=material_map[mat_code],
                    quantity=Decimal(str(qty)),
                    location=location_map[loc_code],
                ))
            StockIssueLine.objects.bulk_create(line_objs)
            try:
                post_stock_issue(issue, user)
                posted += 1
            except Exception as exc:
                issue.delete()
                self.stderr.write(self.style.WARNING(f'  Bỏ qua {number}: {exc}'))
        return posted

    def _create_transfers(self, user, today, material_map, location_map) -> int:
        created = 0
        loc_a1 = location_map['KE-A1']
        loc_xuong = location_map['XUONG-SX']
        loc_pl = location_map['KHO-PL']

        # Đã nhận — chuyển vải xuống xưởng
        t1_num = f'PC-{DEMO_TAG}-2026-001'
        if not StockTransfer.objects.filter(number=t1_num).exists():
            t1 = StockTransfer.objects.create(
                number=t1_num,
                transfer_date=today - timedelta(days=14),
                from_location=loc_a1,
                to_location=loc_xuong,
                created_by=user,
                notes=f'Chuyển vải xuống xưởng may — {DEMO_NOTE}',
            )
            StockTransferLine.objects.create(
                transfer=t1,
                material=material_map['VAI-COT180-BLK'],
                quantity=Decimal('80'),
            )
            StockTransferLine.objects.create(
                transfer=t1,
                material=material_map['VAI-PES4W-220-GRY'],
                quantity=Decimal('50'),
            )
            send_stock_transfer(t1, user)
            receive_stock_transfer(t1, user)
            created += 1

        # Đang chuyển — phụ liệu lẻ
        t2_num = f'PC-{DEMO_TAG}-2026-002'
        if not StockTransfer.objects.filter(number=t2_num).exists():
            t2 = StockTransfer.objects.create(
                number=t2_num,
                transfer_date=today - timedelta(days=3),
                from_location=location_map['KE-B1'],
                to_location=loc_pl,
                created_by=user,
                notes=f'Chuyển phụ liệu lẻ cho xưởng 2 — {DEMO_NOTE}',
            )
            StockTransferLine.objects.create(
                transfer=t2,
                material=material_map['DZ-YKK3-15-BLK'],
                quantity=Decimal('200'),
            )
            StockTransferLine.objects.create(
                transfer=t2,
                material=material_map['NUT-2L-12-BLK'],
                quantity=Decimal('500'),
            )
            send_stock_transfer(t2, user)
            created += 1

        # Nháp
        t3_num = f'PC-{DEMO_TAG}-2026-003'
        if not StockTransfer.objects.filter(number=t3_num).exists():
            t3 = StockTransfer.objects.create(
                number=t3_num,
                transfer_date=today,
                from_location=location_map['KE-B2'],
                to_location=loc_xuong,
                created_by=user,
                notes=f'Chuyển tem nhãn xuống xưởng — {DEMO_NOTE}',
            )
            StockTransferLine.objects.create(
                transfer=t3,
                material=material_map['TEM-SIZE-JP'],
                quantity=Decimal('1000'),
            )
            created += 1

        return created

    def _create_adjustments(self, user, today, material_map, location_map):
        # Đã duyệt — sai lệch sau kiểm kê
        adj1_num = f'DC-{DEMO_TAG}-2026-001'
        if not StockAdjustment.objects.filter(number=adj1_num).exists():
            mat = material_map['VAI-COT180-WHT']
            loc = location_map['KE-A1']
            balance = StockBalance.objects.filter(material=mat, location=loc).first()
            system_qty = balance.quantity if balance else Decimal('0')
            adj = StockAdjustment.objects.create(
                number=adj1_num,
                adjust_date=today - timedelta(days=7),
                reason='Điều chỉnh sau kiểm kê — thiếu 5m do cắt mẫu chưa ghi sổ',
                proposed_by=user,
            )
            StockAdjustmentLine.objects.create(
                adjustment=adj,
                material=mat,
                location=loc,
                system_qty=system_qty,
                actual_qty=max(Decimal('0'), system_qty - Decimal('5')),
            )
            approve_stock_adjustment(adj, user)

        # Chờ duyệt
        adj2_num = f'DC-{DEMO_TAG}-2026-002'
        if not StockAdjustment.objects.filter(number=adj2_num).exists():
            mat = material_map['CHI-PES40-BLK']
            loc = location_map['KE-B1']
            balance = StockBalance.objects.filter(material=mat, location=loc).first()
            system_qty = balance.quantity if balance else Decimal('0')
            adj = StockAdjustment.objects.create(
                number=adj2_num,
                adjust_date=today - timedelta(days=2),
                reason='Thừa 1 cuộn chỉ — nhập nhầm khi kiểm kê',
                proposed_by=user,
            )
            StockAdjustmentLine.objects.create(
                adjustment=adj,
                material=mat,
                location=loc,
                system_qty=system_qty,
                actual_qty=system_qty + Decimal('1'),
            )

    def _create_stocktake(self, user, today, location_map):
        st_num = f'KK-{DEMO_TAG}-2026-001'
        if Stocktake.objects.filter(number=st_num).exists():
            return
        st = Stocktake.objects.create(
            number=st_num,
            name='Kiểm kê định kỳ Q1/2026 — Kệ A1 vải chính',
            stocktake_date=today - timedelta(days=1),
            location=location_map['KE-A1'],
            created_by=user,
            notes=f'Kiểm kê demo — {DEMO_NOTE}',
        )
        start_stocktake_counting(st)
        # Nhập một phần tồn thực tế
        for line in st.lines.all()[:8]:
            line.actual_qty = line.system_qty
            line.save(update_fields=['actual_qty'])
        # 2 dòng lệch để demo
        variance_lines = list(st.lines.all()[8:10])
        for line in variance_lines:
            line.actual_qty = max(Decimal('0'), line.system_qty - Decimal('2'))
            line.save(update_fields=['actual_qty'])

    def _create_disposal(self, user, today, material_map, location_map):
        num = f'PH-{DEMO_TAG}-2026-001'
        if StockDisposal.objects.filter(number=num).exists():
            return
        scrap_loc = WarehouseLocation.objects.filter(code=WAREHOUSE_SCRAP_CODE).first()
        from_loc = location_map['KE-A1']
        disposal = StockDisposal.objects.create(
            number=num,
            disposal_date=today - timedelta(days=6),
            from_location=from_loc,
            reason=DISPOSAL_REASON_DAMAGED,
            created_by=user,
            notes=f'Hủy vải ố vàng do ẩm mốc — {DEMO_NOTE}',
        )
        StockDisposalLine.objects.create(
            disposal=disposal,
            material=material_map['VAI-FLEECE-GRN'],
            quantity=Decimal('3'),
            notes='Cuộn bị thấm nước',
        )
        post_stock_disposal(disposal, user)

    def _print_summary(self):
        mats = Material.objects.filter(code__startswith=MATERIAL_PREFIX).count()
        balances = StockBalance.objects.filter(material__code__startswith=MATERIAL_PREFIX).count()
        low = sum(
            1 for m in Material.objects.filter(code__startswith=MATERIAL_PREFIX).select_related('unit')
            if self._material_is_low(m)
        )
        self.stdout.write(self.style.SUCCESS('\n==> Seed demo done'))
        self.stdout.write(f'  NPL (JP-):        {mats}')
        self.stdout.write(f'  Stock balances:   {balances}')
        self.stdout.write(f'  Low stock items:  {low}')
        self.stdout.write(self.style.WARNING(
            '\nClear: python manage.py seed_kho_npl_demo --clear',
        ))

    def _material_is_low(self, material: Material) -> bool:
        from django.db.models import Sum

        total = (
            StockBalance.objects.filter(material=material)
            .aggregate(total=Sum('quantity'))['total']
            or Decimal('0')
        )
        return Decimal('0') < total <= material.min_stock

    @transaction.atomic
    def _clear_demo_data(self):
        self.stdout.write(self.style.WARNING('==> Clearing demo kho NPL...'))

        demo_materials = Material.objects.filter(code__startswith=MATERIAL_PREFIX)
        demo_ids = list(demo_materials.values_list('pk', flat=True))

        if not demo_ids:
            self.stdout.write('  No demo data (prefix JP-).')
            return

        StockLedger.objects.filter(material_id__in=demo_ids).delete()
        StocktakeLine.objects.filter(material_id__in=demo_ids).delete()
        StockAdjustment.objects.filter(number__contains=f'-{DEMO_TAG}-').delete()
        StockDisposal.objects.filter(number__contains=f'-{DEMO_TAG}-').delete()
        StockTransfer.objects.filter(number__contains=f'-{DEMO_TAG}-').delete()
        StockIssue.objects.filter(number__contains=f'-{DEMO_TAG}-').delete()
        StockReceipt.objects.filter(number__contains=f'-{DEMO_TAG}-').delete()
        Stocktake.objects.filter(number__contains=f'-{DEMO_TAG}-').delete()
        StockBalance.objects.filter(material_id__in=demo_ids).delete()

        deleted, _ = demo_materials.delete()
        self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted} related records.'))
