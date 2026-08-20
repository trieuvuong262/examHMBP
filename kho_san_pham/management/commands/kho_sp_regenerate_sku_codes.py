"""Sinh lại ``Product.code`` cho khớp bộ thuộc tính đã chuẩn hóa.

Trước lệnh này, mã SKU và thuộc tính nói hai chuyện khác nhau: mã còn mang size
cũ (``...-XXL`` khi ``size_label='2XL'``) và token màu tiếng Việt (``-TRNG-``,
``-XM-``), hoặc không có màu. Ngoài chuyện khó đọc, ``parse_sku_code`` tách mã
ngược ra sẽ cho màu/size không thuộc từ vựng rồi tạo rác vào danh mục.

Mã mới: ``{style}[-{màu}]-{size}[-{giới tính}]`` — bỏ màu khi ``NOCOLOR``.

Chỉ đổi sản phẩm **đang dùng**. Sản phẩm đã ngừng giữ mã cũ: chúng là lịch sử,
không ai tham chiếu tới nữa, mà đổi thì thêm nguy cơ đụng mã.

Mã cũ lưu vào ``legacy_code``. Đổi kèm ``SxSku.sku_code`` và các cột ``sku_code``
chuỗi tự do trong ``san_xuat`` để không dòng nào bị treo.

Mặc định chỉ xem trước. Thêm ``--apply`` để ghi DB.
"""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from kho_san_pham.choices import DEFAULT_BRAND, PRODUCT_TYPE_THANH_PHAM
from kho_san_pham.models import Product
from san_xuat.hub_models import (
    SxFgReceiptLine,
    SxPackingLine,
    SxProductionOrderLine,
    SxProductionStat,
    SxQcRequest,
    SxSku,
)
from san_xuat.services.sku_catalog import SkuError, compose_sku_code

# Các bảng lưu mã SKU dưới dạng chuỗi tự do (không phải khóa ngoại). Đổi mã mà bỏ
# sót thì những dòng này trỏ vào mã không còn tồn tại.
FREE_TEXT_MODELS = (
    SxProductionOrderLine,
    SxProductionStat,
    SxQcRequest,
    SxPackingLine,
    SxFgReceiptLine,
)


class Command(BaseCommand):
    help = 'Sinh lại mã SKU theo từ vựng chuẩn. Mặc định xem trước; dùng --apply để ghi DB.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Ghi DB (mặc định chỉ xem trước).',
        )
        parser.add_argument(
            '--limit-report', type=int, default=15,
            help='Số dòng ví dụ in ra mỗi mục.',
        )

    def handle(self, *args, **options):
        self.apply = options['apply']
        self.limit = max(1, options['limit_report'])

        products = list(
            Product.objects.filter(is_active=True, product_type=PRODUCT_TYPE_THANH_PHAM)
            .order_by('code')
        )
        plan, skipped = self._build_plan(products)
        self._check_collisions(plan, products)

        self._report_plan(plan, skipped)

        if not self.apply:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Xem trước — chưa ghi gì. Thêm --apply để ghi DB.'))
            return

        with transaction.atomic():
            self._write_products(plan)
            sku_updated = self._write_sx_skus(plan)
            free_text = self._write_free_text(plan)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Đã đổi {len(plan)} mã sản phẩm.'))
        self.stdout.write(f'SxSku đổi theo: {sku_updated}')
        for name, count in free_text.items():
            if count:
                self.stdout.write(f'{name}: {count} dòng cập nhật sku_code')

    # ---- lập kế hoạch

    def _build_plan(self, products):
        """Trả (danh sách (product, mã mới), lý do bỏ qua)."""
        plan: list[tuple[Product, str]] = []
        skipped: Counter = Counter()

        for product in products:
            # Style phải là mã chuẩn JP-… Vài dòng có style_code bằng chính tên sản
            # phẩm (sync đặt style tạm khi chưa map được loại mã); ghép vào sẽ ra mã
            # kiểu "DỊCH VỤ IN TÊN CHỮ…-NOSIZE" — có dấu, có khoảng trắng, vô dụng.
            # Mã KiotViet cũ của chúng tốt hơn, nên giữ nguyên.
            if not (product.style_code or '').upper().startswith(f'{DEFAULT_BRAND}-'):
                skipped['style không phải mã chuẩn JP-'] += 1
                self.style_review.append(f'{product.code} (style: {product.style_code})')
                continue
            try:
                new_code = compose_sku_code(
                    style_code=product.style_code,
                    color_code=product.color_code,
                    size_label=product.size_label,
                    gender=product.gender,
                )
            except SkuError as exc:
                skipped[str(exc)] += 1
                continue
            if new_code == product.code:
                skipped['mã đã đúng'] += 1
                continue
            plan.append((product, new_code))
        return plan, skipped

    def _check_collisions(self, plan, products):
        """Dừng trước khi ghi nếu mã mới đụng nhau hoặc đụng mã đang tồn tại.

        Thà dừng còn hơn ghi được một nửa rồi vỡ ở giữa vì ràng buộc unique.
        """
        new_codes: dict[str, list[str]] = defaultdict(list)
        for product, new_code in plan:
            new_codes[new_code].append(product.code)

        internal = {code: olds for code, olds in new_codes.items() if len(olds) > 1}
        if internal:
            lines = [f'  {code} <- {", ".join(olds)}' for code, olds in list(internal.items())[:20]]
            raise CommandError(
                f'{len(internal)} mã mới bị hai sản phẩm trở lên dùng chung:\n'
                + '\n'.join(lines)
                + '\nBộ (style, màu, size, giới tính) phải phân biệt được từng SKU.'
            )

        # Mã mới có thể đụng mã của sản phẩm khác đang giữ nguyên (kể cả đã ngừng dùng).
        changing_pks = {p.pk for p, _ in plan}
        clashes = list(
            Product.objects.filter(code__in=list(new_codes))
            .exclude(pk__in=changing_pks)
            .values_list('code', 'is_active')
        )
        if clashes:
            lines = [
                f'  {code} (đang dùng)' if active else f'  {code} (đã ngừng)'
                for code, active in list(clashes)[:20]
            ]
            raise CommandError(
                f'{len(clashes)} mã mới đụng sản phẩm khác không nằm trong đợt đổi:\n'
                + '\n'.join(lines)
            )

    # ---- báo cáo

    def _report_plan(self, plan, skipped):
        mode = 'ĐÃ GHI DB' if self.apply else 'XEM TRƯỚC (chưa ghi gì)'
        self.stdout.write(f'--- Sinh lại mã SKU — {mode} ---')
        self.stdout.write(f'Số mã sẽ đổi: {len(plan)}')
        for reason, count in skipped.most_common():
            self.stdout.write(f'Bỏ qua ({reason}): {count}')

        if not plan:
            return

        kinds = Counter()
        for product, new_code in plan:
            if product.color_code and product.color_code != 'NOCOLOR' and product.color_code not in product.code:
                kinds['thêm mã màu chuẩn vào mã'] += 1
            if not product.code.endswith(f'-{product.size_label}'):
                kinds['sửa phần size'] += 1
            if product.gender and not product.code.endswith(f'-{product.gender}'):
                kinds['sửa phần giới tính'] += 1

        self.stdout.write('')
        for kind, count in kinds.most_common():
            self.stdout.write(f'  {kind}: {count}')

        self.stdout.write('')
        self.stdout.write('Ví dụ:')
        for product, new_code in plan[: self.limit]:
            self.stdout.write(f'  {product.code}')
            self.stdout.write(f'    -> {new_code}')

    # ---- ghi

    def _write_products(self, plan):
        """Đổi mã qua hai lượt để không đụng ràng buộc unique giữa đường.

        Mã mới của sản phẩm A có thể đang là mã cũ của sản phẩm B (vd. đổi phần
        size làm hai mã đổi chỗ nhau). Ghi trực tiếp là vỡ unique, nên lượt một
        dồn hết sang mã tạm.
        """
        for product, _new_code in plan:
            Product.objects.filter(pk=product.pk).update(code=f'~TMP~{product.pk}')

        for product, new_code in plan:
            Product.objects.filter(pk=product.pk).update(
                code=new_code,
                legacy_code=product.code,
            )

    def _write_sx_skus(self, plan):
        """Đổi ``SxSku.sku_code`` theo, cũng qua hai lượt vì cột này unique."""
        pairs = []
        for product, new_code in plan:
            if product.sx_sku_id:
                pairs.append((product.sx_sku_id, new_code))
        if not pairs:
            return 0

        for sku_id, _new_code in pairs:
            SxSku.objects.filter(pk=sku_id).update(sku_code=f'~TMP~{sku_id}')
        for sku_id, new_code in pairs:
            SxSku.objects.filter(pk=sku_id).update(sku_code=new_code)
        return len(pairs)

    def _write_free_text(self, plan):
        """Đổi các cột ``sku_code`` chuỗi tự do. Không unique nên đổi thẳng.

        Lọc ra dòng cần đổi trước rồi mới ghi, thay vì chạy một UPDATE cho từng
        mã trong 2.900 mã — số dòng thực tế chỉ vài trăm.
        """
        mapping = {product.code: new_code for product, new_code in plan}
        counts: dict[str, int] = {}
        for model in FREE_TEXT_MODELS:
            rows = list(
                model.objects.filter(sku_code__in=mapping.keys()).values_list('pk', 'sku_code')
            )
            for pk, old_code in rows:
                model.objects.filter(pk=pk).update(sku_code=mapping[old_code])
            counts[model.__name__] = len(rows)
        return counts
