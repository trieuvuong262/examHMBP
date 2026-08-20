"""Chuẩn hóa từ vựng SKU của kho sản phẩm: danh mục size, danh mục màu, và các cột
``size_label`` / ``gender`` / ``color_code`` / ``color_label`` trên từng sản phẩm.

Mặc định chỉ xem trước. Thêm ``--apply`` để ghi DB.
``Product.code`` không bị sinh lại — mã SKU là mã bất biến.
"""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from kho_san_pham.models import Product
from kho_san_pham.sku_vocabulary import (
    CANONICAL_SIZES,
    COLOR_CODES,
    COLOR_NONE,
    COLOR_NONE_LABEL,
    GENDER_NONE,
    build_color_label,
    normalize_size,
    resolve_color,
)
from san_xuat.hub_models import SxColor, SxSize

_COLOR_SORT_STEP = 10
_REVIEW_SAMPLE = 15


class Command(BaseCommand):
    help = (
        'Chuẩn hóa danh mục size/màu và các cột size_label, gender, color_code, '
        'color_label của kho sản phẩm. Mặc định xem trước; dùng --apply để ghi DB.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Ghi DB (mặc định chỉ xem trước).',
        )

    def handle(self, *args, **options):
        self.apply = options['apply']
        with transaction.atomic():
            self._sync_sizes()
            combo_labels = self._plan_products()
            self._sync_colors(combo_labels)
            self._write_products()
            if not self.apply:
                transaction.set_rollback(True)
        self._report()

    # ------------------------------------------------------------ danh mục size

    def _sync_sizes(self):
        self.size_created: list[str] = []
        self.size_updated: list[str] = []
        self.size_retired: list[str] = []

        canonical_codes = set()
        for scale, code, name, sort_order in CANONICAL_SIZES:
            canonical_codes.add(code)
            row = SxSize.objects.filter(code=code).first()
            if row is None:
                if self.apply:
                    SxSize.objects.create(
                        code=code, name=name, scale=scale, sort_order=sort_order, is_active=True
                    )
                self.size_created.append(f'{code} ({scale}, thứ tự {sort_order})')
                continue
            changes = []
            if row.scale != scale:
                changes.append(f'thang đo {row.scale or "—"}→{scale}')
                row.scale = scale
            if row.sort_order != sort_order:
                changes.append(f'thứ tự {row.sort_order}→{sort_order}')
                row.sort_order = sort_order
            if not row.name:
                row.name = name
                changes.append('bổ sung tên')
            if not row.is_active:
                row.is_active = True
                changes.append('bật lại')
            if changes:
                if self.apply:
                    row.save(update_fields=['name', 'scale', 'sort_order', 'is_active'])
                self.size_updated.append(f'{code}: {", ".join(changes)}')

        # Cách viết cũ (XXL, XXXL) đã có mã chuẩn thay thế → ngừng dùng, không xóa.
        for row in SxSize.objects.exclude(code__in=canonical_codes).filter(is_active=True):
            if self.apply:
                row.is_active = False
                row.save(update_fields=['is_active'])
            self.size_retired.append(row.code)

    # ------------------------------------------------------------ danh mục màu

    def _sync_colors(self, combo_labels: dict[str, tuple[str, ...]]):
        self.color_created: list[str] = []
        self.color_updated: list[str] = []

        wanted: list[tuple[str, str]] = [(code, name) for name, code in COLOR_CODES.items()]
        wanted += [
            (code, build_color_label(parts))
            for code, parts in sorted(combo_labels.items())
        ]
        wanted.append((COLOR_NONE, COLOR_NONE_LABEL))

        existing = {row.code: row for row in SxColor.objects.all()}
        next_order = max((row.sort_order for row in existing.values()), default=0)

        for code, name in wanted:
            row = existing.get(code)
            if row is None:
                next_order += _COLOR_SORT_STEP
                if self.apply:
                    SxColor.objects.create(code=code, name=name, sort_order=next_order, is_active=True)
                self.color_created.append(f'{code} — {name}')
                continue
            changes = []
            if row.name != name:
                changes.append(f'"{row.name}"→"{name}"')
                row.name = name
            if not row.is_active:
                row.is_active = True
                changes.append('bật lại')
            if changes:
                if self.apply:
                    row.save(update_fields=['name', 'is_active'])
                self.color_updated.append(f'{code}: {", ".join(changes)}')

    # ------------------------------------------------------------ sản phẩm

    def _plan_products(self) -> dict[str, tuple[str, ...]]:
        """Tính giá trị chuẩn cho từng sản phẩm; trả về các mã tổ hợp màu cần tạo."""
        self.pending: list[tuple[Product, list[str]]] = []
        self.size_changes = Counter()
        self.gender_changes = Counter()
        self.color_changes = Counter()
        self.color_none_count = 0
        self.size_review: dict[str, list[str]] = defaultdict(list)
        self.color_review: dict[str, list[str]] = defaultdict(list)

        combo_labels: dict[str, tuple[str, ...]] = {}

        for product in Product.objects.all().iterator(chunk_size=1000):
            changed: list[str] = []

            size = normalize_size(product.size_label, product.name)
            if size.needs_review:
                self.size_review[size.reason].append(product.code)
            else:
                if size.size_code != product.size_label:
                    self.size_changes[f'{product.size_label or "(trống)"} → {size.size_code}'] += 1
                    product.size_label = size.size_code
                    changed.append('size_label')
                if size.gender != GENDER_NONE and product.gender != size.gender:
                    self.gender_changes[size.gender] += 1
                    product.gender = size.gender
                    changed.append('gender')

            color = resolve_color(product.name, product.full_name, product.color_label)
            if color.resolved:
                if color.is_combo:
                    combo_labels[color.code] = color.parts
                if product.color_code != color.code:
                    product.color_code = color.code
                    changed.append('color_code')
                if product.color_label != color.label:
                    product.color_label = color.label
                    changed.append('color_label')
                if 'color_code' in changed or 'color_label' in changed:
                    self.color_changes[f'{color.code} ({color.source})'] += 1
            else:
                self.color_review[color.reason].append(product.code)
                # Chốt "không có màu" để bộ ba style–màu–size luôn đủ chiều. Giữ nguyên
                # color_label vì đó là dấu vết duy nhất trong DB cho biết vì sao cần rà.
                if product.color_code != COLOR_NONE:
                    product.color_code = COLOR_NONE
                    changed.append('color_code')
                    self.color_none_count += 1

            if changed:
                self.pending.append((product, changed))

        return combo_labels

    def _write_products(self):
        if not self.apply:
            return
        for product, changed in self.pending:
            product.save(update_fields=[*changed, 'updated_at'])

    # ------------------------------------------------------------ báo cáo

    def _report(self):
        out = self.stdout
        mode = 'ĐÃ GHI DB' if self.apply else 'XEM TRƯỚC (chưa ghi gì)'
        out.write(self.style.MIGRATE_HEADING(f'\n=== {mode} ==='))

        out.write(self.style.MIGRATE_HEADING('\nDanh mục size'))
        self._write_list('Tạo mới', self.size_created)
        self._write_list('Sửa', self.size_updated)
        self._write_list('Ngừng dùng (đã có mã chuẩn thay thế)', self.size_retired)

        out.write(self.style.MIGRATE_HEADING('\nDanh mục màu'))
        self._write_list('Tạo mới', self.color_created)
        self._write_list('Sửa tên', self.color_updated)

        out.write(self.style.MIGRATE_HEADING('\nSản phẩm'))
        out.write(f'  Số dòng thay đổi: {len(self.pending)}')
        self._write_counter('Chuẩn hóa size', self.size_changes)
        self._write_counter('Tách giới tính khỏi size', self.gender_changes)
        self._write_counter('Gán mã màu', self.color_changes)
        if self.color_none_count:
            out.write(f'  Chốt {COLOR_NONE}: {self.color_none_count}')

        review_codes = {code for codes in self.size_review.values() for code in codes}
        review_codes |= {code for codes in self.color_review.values() for code in codes}
        if review_codes:
            out.write(
                self.style.WARNING(
                    f'\nĐã chốt "không có màu", nghiệp vụ rà lại sau: {len(review_codes)} SKU'
                )
            )
            for reason, codes in sorted(self.size_review.items(), key=lambda x: -len(x[1])):
                self._write_review(reason, codes)
            for reason, codes in sorted(self.color_review.items(), key=lambda x: -len(x[1])):
                self._write_review(reason, codes)

        if not self.apply:
            out.write(self.style.NOTICE('\nChạy lại với --apply để ghi DB.'))

    def _write_list(self, title: str, items: list[str]):
        if not items:
            return
        self.stdout.write(f'  {title}: {len(items)}')
        for item in items:
            self.stdout.write(f'    - {item}')

    def _write_counter(self, title: str, counter: Counter, limit: int | None = None):
        if not counter:
            return
        self.stdout.write(f'  {title}: {sum(counter.values())}')
        for key, count in counter.most_common(limit):
            self.stdout.write(f'    [{count}] {key}')

    def _write_review(self, reason: str, codes: list[str]):
        sample = ', '.join(codes[:_REVIEW_SAMPLE])
        more = f' … (+{len(codes) - _REVIEW_SAMPLE})' if len(codes) > _REVIEW_SAMPLE else ''
        self.stdout.write(f'  [{len(codes)}] {reason}')
        self.stdout.write(f'      {sample}{more}')
