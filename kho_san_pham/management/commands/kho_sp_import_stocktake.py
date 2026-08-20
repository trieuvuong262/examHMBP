"""Nhập kết quả kiểm kê vào sổ kho — dùng cho tồn đầu kỳ.

Tồn đầu kỳ **phải đếm thực tế**, không bốc từ KiotViet sang: tồn KiotViet mang
sẵn sai số tích lũy nhiều năm, nhập nó vào là kế thừa nguyên vẹn sai số đó rồi
mất luôn khả năng phân biệt "lệch do lịch sử" với "lệch do hệ mới ghi sai".

Lệnh này ghi phần **chênh lệch** giữa số đếm được và số sổ đang có, dưới dạng
``kind=adjust``. Nên nó dùng được cả cho tồn đầu kỳ (sổ đang trống) và cho kiểm
kê định kỳ về sau.

Mặc định chỉ xem trước, phải có ``--apply`` mới ghi.

    manage.py kho_sp_import_stocktake --warehouse XUONG-TP --file kk.csv
    manage.py kho_sp_import_stocktake --warehouse XUONG-TP --file kk.csv --apply

Tệp CSV cần hai cột ``sku_code`` và ``qty_counted``; cột khác bỏ qua.
"""

import csv
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from kho_san_pham.choices import DOC_TYPE_STOCKTAKE, MOVEMENT_ADJUST, SOURCE_SYSTEM_PORTAL
from kho_san_pham.models import Product, Warehouse
from kho_san_pham.services.stock import StockMovementError, get_qty_on_hand, post_movement

REQUIRED_COLUMNS = ('sku_code', 'qty_counted')


class Command(BaseCommand):
    help = 'Nhập kết quả kiểm kê (tồn đầu kỳ) vào sổ kho thành phẩm.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--warehouse', required=True,
            help='Mã kho được kiểm kê, ví dụ XUONG-TP.',
        )
        parser.add_argument(
            '--file', required=True,
            help='Đường dẫn tệp CSV: sku_code,qty_counted.',
        )
        parser.add_argument(
            '--code', default='',
            help='Số phiếu kiểm kê. Bỏ trống thì tự đặt KK-<ngày>-<mã kho>.',
        )
        parser.add_argument(
            '--date', default='',
            help='Ngày kiểm kê YYYY-MM-DD. Bỏ trống thì lấy hôm nay.',
        )
        parser.add_argument(
            '--skip-unknown', action='store_true',
            help='Bỏ qua SKU không có trong danh mục thay vì dừng.',
        )
        parser.add_argument(
            '--apply', action='store_true',
            help='Ghi thật. Không có cờ này thì chỉ xem trước.',
        )

    def handle(self, *args, **options):
        warehouse = self._get_warehouse(options['warehouse'])
        stock_date = self._get_date(options['date'])
        doc_code = (options['code'] or '').strip() or f'KK-{stock_date:%Y%m%d}-{warehouse.code}'
        rows = self._read_csv(options['file'])
        apply_changes = options['apply']

        self.stdout.write(f'Kho:    {warehouse.code} — {warehouse.name}')
        self.stdout.write(f'Phiếu:  {doc_code} (ngày {stock_date:%d/%m/%Y})')
        self.stdout.write(f'Đọc được {len(rows)} dòng từ tệp.')
        self.stdout.write('')

        plan, unknown = self._build_plan(rows, warehouse)

        if unknown:
            self.stdout.write(self.style.WARNING(f'{len(unknown)} SKU không có trong danh mục:'))
            for code in unknown[:20]:
                self.stdout.write(f'  - {code}')
            if len(unknown) > 20:
                self.stdout.write(f'  … và {len(unknown) - 20} mã nữa')
            if not options['skip_unknown']:
                raise CommandError(
                    'Dừng vì có SKU lạ. Tồn đầu kỳ nhập thiếu thì sai ngay từ gốc — '
                    'hãy bổ sung SKU vào danh mục, hoặc dùng --skip-unknown nếu cố ý bỏ.'
                )
            self.stdout.write('')

        self._report_plan(plan)

        if not apply_changes:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Chỉ xem trước — thêm --apply để ghi thật.'))
            return

        applied, already = self._write(plan, warehouse, doc_code, stock_date)
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Đã ghi {applied} phát sinh điều chỉnh.'))
        if already:
            self.stdout.write(f'{already} dòng đã ghi từ trước, bỏ qua (phiếu {doc_code}).')

    # ---- đọc dữ liệu vào

    def _get_warehouse(self, code: str) -> Warehouse:
        wh = Warehouse.objects.filter(code=(code or '').strip().upper()).first()
        if wh is None:
            available = ', '.join(Warehouse.objects.values_list('code', flat=True)) or '(chưa có kho nào)'
            raise CommandError(f'Không có kho mã {code!r}. Đang có: {available}')
        if not wh.is_active:
            raise CommandError(f'Kho {wh.code} đang ngừng dùng.')
        return wh

    def _get_date(self, raw: str):
        raw = (raw or '').strip()
        if not raw:
            return timezone.localdate()
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError as exc:
            raise CommandError(f'Ngày không đúng dạng YYYY-MM-DD: {raw!r}') from exc

    def _read_csv(self, path_str: str) -> list[tuple[str, Decimal]]:
        path = Path(path_str)
        if not path.exists():
            raise CommandError(f'Không thấy tệp: {path}')

        # utf-8-sig: Excel xuất CSV kèm BOM, để utf-8 thường thì tên cột đầu
        # tiên dính ký tự lạ và không khớp được.
        with path.open(newline='', encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise CommandError(
                    f'Tệp thiếu cột: {", ".join(missing)}. '
                    f'Đang có: {", ".join(reader.fieldnames or []) or "(không đọc được tiêu đề)"}'
                )

            rows: list[tuple[str, Decimal]] = []
            seen: dict[str, int] = {}
            for line_no, raw in enumerate(reader, start=2):
                code = (raw.get('sku_code') or '').strip().upper()
                if not code:
                    continue
                if code in seen:
                    raise CommandError(
                        f'SKU {code} xuất hiện hai lần (dòng {seen[code]} và {line_no}). '
                        'Một phiếu kiểm kê chỉ được có một dòng cho mỗi SKU.'
                    )
                seen[code] = line_no
                rows.append((code, self._parse_qty(raw.get('qty_counted'), code, line_no)))
        if not rows:
            raise CommandError('Tệp không có dòng dữ liệu nào.')
        return rows

    def _parse_qty(self, raw, code: str, line_no: int) -> Decimal:
        text = (raw or '').strip().replace(',', '')
        if not text:
            raise CommandError(f'Dòng {line_no} ({code}): thiếu qty_counted.')
        try:
            qty = Decimal(text)
        except InvalidOperation as exc:
            raise CommandError(f'Dòng {line_no} ({code}): qty_counted không phải số: {raw!r}') from exc
        if qty < 0:
            raise CommandError(f'Dòng {line_no} ({code}): số đếm không thể âm ({qty}).')
        return qty.quantize(Decimal('0.01'))

    # ---- tính chênh lệch

    def _build_plan(self, rows, warehouse):
        """Ghép từng dòng với sản phẩm và tính chênh lệch so với sổ."""
        codes = [code for code, _ in rows]
        by_code = {p.code.upper(): p for p in Product.objects.filter(code__in=codes)}

        plan = []
        unknown = []
        for code, counted in rows:
            product = by_code.get(code)
            if product is None:
                unknown.append(code)
                continue
            on_book = get_qty_on_hand(product, warehouse)
            plan.append({
                'product': product,
                'counted': counted,
                'on_book': on_book,
                'delta': counted - on_book,
            })
        return plan, unknown

    def _report_plan(self, plan):
        changed = [r for r in plan if r['delta'] != 0]
        same = len(plan) - len(changed)

        total_counted = sum((r['counted'] for r in plan), Decimal('0'))
        self.stdout.write(f'Khớp sổ, không cần ghi: {same} SKU')
        self.stdout.write(f'Cần ghi điều chỉnh:     {len(changed)} SKU')
        self.stdout.write(f'Tổng số đếm được:       {total_counted}')

        if not changed:
            return
        self.stdout.write('')
        self.stdout.write(f'{"SKU":<32} {"Sổ":>10} {"Đếm":>10} {"Chênh":>10}')
        for row in changed[:30]:
            self.stdout.write(
                f'{row["product"].code:<32} {row["on_book"]:>10} '
                f'{row["counted"]:>10} {row["delta"]:>+10}'
            )
        if len(changed) > 30:
            self.stdout.write(f'… và {len(changed) - 30} SKU nữa')

    # ---- ghi

    def _write(self, plan, warehouse, doc_code, stock_date):
        occurred_at = self._occurred_at(stock_date)
        applied = 0
        already = 0

        for row in plan:
            if row['delta'] == 0:
                continue
            product = row['product']
            try:
                # Mỗi SKU ghi trong transaction riêng: một dòng lỗi không nên
                # xóa công của cả phiếu vài nghìn dòng.
                with transaction.atomic():
                    result = post_movement(
                        product=product,
                        warehouse=warehouse,
                        kind=MOVEMENT_ADJUST,
                        qty_delta=row['delta'],
                        source_system=SOURCE_SYSTEM_PORTAL,
                        source_doc_type=DOC_TYPE_STOCKTAKE,
                        source_doc_code=doc_code,
                        # id sản phẩm, không phải số dòng trong tệp: chạy lại với
                        # tệp sắp xếp khác thì số dòng đổi và khóa chống trùng
                        # mất tác dụng.
                        source_line_no=product.pk,
                        occurred_at=occurred_at,
                        actor='kho_sp_import_stocktake',
                        notes=f'Kiểm kê {doc_code}: sổ {row["on_book"]} → đếm {row["counted"]}',
                    )
            except StockMovementError as exc:
                raise CommandError(f'{product.code}: {exc}') from exc

            if result.was_applied:
                applied += 1
            else:
                already += 1
        return applied, already

    def _occurred_at(self, stock_date):
        naive = datetime.combine(stock_date, time.min)
        return timezone.make_aware(naive) if settings.USE_TZ else naive
