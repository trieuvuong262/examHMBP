"""Xuất / nhập Excel danh mục kho sản phẩm (SKU = Style–Màu–Size)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pandas as pd
from django.http import HttpResponse

from kho_npl.services.excel_export import dataframe_to_xlsx_response
from kho_san_pham.choices import (
    PRODUCT_TYPE_HANG_HOA,
    PRODUCT_TYPE_LABELS,
    PRODUCT_TYPE_THANH_PHAM,
    SYNC_SOURCE_MANUAL,
)
from kho_san_pham.models import Product

EXCEL_HEADERS = [
    'SKU',
    'Style',
    'Mã màu',
    'Tên màu',
    'Size',
    'Mã kế toán',
    'Mã KiotViet',
    'Tên',
    'Tên đầy đủ',
    'Loại',
    'Mã vạch',
    'ĐVT',
    'Nhóm hàng',
    'Giá bán',
    'Mô tả',
    'Ghi chú',
    'Đang dùng',
]

_HEADER_ALIASES = {
    'sku': 'SKU',
    'ma san pham': 'SKU',
    'ma sp': 'SKU',
    'ma': 'SKU',
    'style': 'Style',
    'ma style': 'Style',
    'ma mau': 'Mã màu',
    'mau': 'Mã màu',
    'ten mau': 'Tên màu',
    'size': 'Size',
    'ma ke toan': 'Mã kế toán',
    'ma kt': 'Mã kế toán',
    'ma kiotviet': 'Mã KiotViet',
    'ma kv': 'Mã KiotViet',
    'ten': 'Tên',
    'ten san pham': 'Tên',
    'ten day du': 'Tên đầy đủ',
    'loai': 'Loại',
    'ma vach': 'Mã vạch',
    'barcode': 'Mã vạch',
    'dvt': 'ĐVT',
    'don vi tinh': 'ĐVT',
    'nhom hang': 'Nhóm hàng',
    'nhom': 'Nhóm hàng',
    'gia ban': 'Giá bán',
    'gia': 'Giá bán',
    'mo ta': 'Mô tả',
    'ghi chu': 'Ghi chú',
    'dang dung': 'Đang dùng',
    'trang thai': 'Đang dùng',
}

_TYPE_ALIASES = {
    'thanh pham': PRODUCT_TYPE_THANH_PHAM,
    'thành phẩm': PRODUCT_TYPE_THANH_PHAM,
    'thanh_pham': PRODUCT_TYPE_THANH_PHAM,
    PRODUCT_TYPE_THANH_PHAM: PRODUCT_TYPE_THANH_PHAM,
    'hang hoa': PRODUCT_TYPE_HANG_HOA,
    'hàng hoá': PRODUCT_TYPE_HANG_HOA,
    'hang hoá': PRODUCT_TYPE_HANG_HOA,
    'hàng hóa': PRODUCT_TYPE_HANG_HOA,
    'hang_hoa': PRODUCT_TYPE_HANG_HOA,
    PRODUCT_TYPE_HANG_HOA: PRODUCT_TYPE_HANG_HOA,
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for col in df.columns:
        key = str(col).strip().lower()
        key_ascii = (
            key.replace('ă', 'a').replace('â', 'a').replace('á', 'a').replace('à', 'a')
            .replace('ả', 'a').replace('ã', 'a').replace('ạ', 'a')
            .replace('đ', 'd')
            .replace('ê', 'e').replace('é', 'e').replace('è', 'e')
            .replace('ẻ', 'e').replace('ẽ', 'e').replace('ẹ', 'e')
            .replace('ô', 'o').replace('ơ', 'o').replace('ó', 'o').replace('ò', 'o')
            .replace('ỏ', 'o').replace('õ', 'o').replace('ọ', 'o')
            .replace('ư', 'u').replace('ú', 'u').replace('ù', 'u')
            .replace('ủ', 'u').replace('ũ', 'u').replace('ụ', 'u')
            .replace('í', 'i').replace('ì', 'i').replace('ỉ', 'i')
            .replace('ĩ', 'i').replace('ị', 'i')
            .replace('ý', 'y').replace('ỳ', 'y').replace('ỷ', 'y')
            .replace('ỹ', 'y').replace('ỵ', 'y')
        )
        mapping[col] = _HEADER_ALIASES.get(key_ascii, _HEADER_ALIASES.get(key, str(col).strip()))
    return df.rename(columns=mapping)


def _parse_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ''
    text = str(value).strip()
    if text.lower() in ('nan', 'none'):
        return ''
    return text


def _parse_bool(value) -> bool:
    text = str(value or '').strip().lower()
    if text in ('', 'nan', 'none'):
        return True
    if text in ('1', 'true', 'yes', 'y', 'co', 'có', 'dang dung', 'đang dùng', 'x'):
        return True
    if text in ('0', 'false', 'no', 'n', 'khong', 'không', 'ngung', 'ngừng'):
        return False
    return True


def _parse_decimal(value, default=Decimal('0')) -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    if not text or text.lower() == 'nan':
        return default
    try:
        return Decimal(text.replace(',', ''))
    except (InvalidOperation, ValueError):
        return default


def _parse_product_type(value) -> str:
    text = _parse_text(value).lower()
    if not text:
        return PRODUCT_TYPE_HANG_HOA
    return _TYPE_ALIASES.get(text, PRODUCT_TYPE_HANG_HOA)


def product_to_row(product: Product) -> dict:
    return {
        'SKU': product.code,
        'Style': product.style_code or '',
        'Mã màu': product.color_code or '',
        'Tên màu': product.color_label or '',
        'Size': product.size_label or '',
        'Mã kế toán': product.accounting_code or '',
        'Mã KiotViet': product.kiotviet_code or '',
        'Tên': product.name,
        'Tên đầy đủ': product.full_name or '',
        'Loại': PRODUCT_TYPE_LABELS.get(product.product_type, product.product_type),
        'Mã vạch': product.bar_code or '',
        'ĐVT': product.unit or '',
        'Nhóm hàng': product.category_name or '',
        'Giá bán': float(product.base_price or 0),
        'Mô tả': product.description or '',
        'Ghi chú': product.notes or '',
        'Đang dùng': 'Có' if product.is_active else 'Không',
    }


def products_to_dataframe(qs) -> pd.DataFrame:
    rows = [product_to_row(p) for p in qs]
    if not rows:
        return pd.DataFrame(columns=EXCEL_HEADERS)
    return pd.DataFrame(rows, columns=EXCEL_HEADERS)


def export_products_xlsx(qs) -> HttpResponse:
    df = products_to_dataframe(qs.order_by('style_code', 'color_code', 'size_label', 'code'))
    return dataframe_to_xlsx_response(df, 'danh_muc_kho_sp', sheet_name='Danh_muc_SP')


def sample_template_xlsx() -> HttpResponse:
    sample = pd.DataFrame([{
        'SKU': 'JP-TEE-260001-NVY-M',
        'Style': 'JP-TEE-260001',
        'Mã màu': 'NVY',
        'Tên màu': 'Navy',
        'Size': 'M',
        'Mã kế toán': 'KT-001',
        'Mã KiotViet': '',
        'Tên': 'Tee Navy M',
        'Tên đầy đủ': '',
        'Loại': 'Hàng hoá',
        'Mã vạch': '',
        'ĐVT': 'Cái',
        'Nhóm hàng': '',
        'Giá bán': 100000,
        'Mô tả': '',
        'Ghi chú': '',
        'Đang dùng': 'Có',
    }], columns=EXCEL_HEADERS)
    return dataframe_to_xlsx_response(sample, 'mau_danh_muc_kho_sp', sheet_name='Mau_SP')


class ProductImportError(Exception):
    pass


def import_products_from_excel(file_obj, *, user=None) -> dict:
    """Import danh mục — tạo mới hoặc cập nhật theo SKU."""
    from san_xuat.services.sku_catalog import (
        SkuError,
        compose_sku_code,
        get_or_create_sku,
        normalize_style,
        normalize_token,
        parse_sku_code,
    )

    try:
        df = pd.read_excel(file_obj)
    except Exception as exc:
        raise ProductImportError(f'Không đọc được file Excel: {exc}') from exc

    if df.empty:
        raise ProductImportError('File Excel không có dữ liệu.')

    df = _normalize_columns(df)
    # Chấp nhận cột cũ «Mã sản phẩm» đã map thành SKU qua alias
    if 'SKU' not in df.columns and 'Tên' not in df.columns:
        raise ProductImportError('Thiếu cột bắt buộc: SKU hoặc Tên.')

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for idx, row in df.iterrows():
        line_no = int(idx) + 2
        style = normalize_style(_parse_text(row.get('Style')))
        color = normalize_token(_parse_text(row.get('Mã màu')))
        size = normalize_token(_parse_text(row.get('Size')))
        color_label = _parse_text(row.get('Tên màu'))
        code = _parse_text(row.get('SKU')).upper()
        name = _parse_text(row.get('Tên'))

        if style and size:
            try:
                code = compose_sku_code(style_code=style, color_code=color, size_label=size)
            except SkuError as exc:
                errors.append(f'Dòng {line_no}: {exc}')
                skipped += 1
                continue
        elif code and (not style or not size):
            parsed = parse_sku_code(code, style_hint=style)
            if parsed:
                style, color, size = parsed

        if not code and not name:
            skipped += 1
            continue
        if not code:
            errors.append(f'Dòng {line_no}: thiếu SKU (hoặc Style+Size).')
            skipped += 1
            continue
        if not name:
            name = style or code

        accounting_code = _parse_text(row.get('Mã kế toán'))

        existing = Product.objects.filter(code__iexact=code).first()
        product_type = _parse_product_type(row.get('Loại'))
        is_active = _parse_bool(row.get('Đang dùng'))
        notes = _parse_text(row.get('Ghi chú'))

        defaults = {
            'style_code': style,
            'color_code': color,
            'color_label': color_label,
            'size_label': size,
            'accounting_code': accounting_code,
            'name': name,
            'full_name': _parse_text(row.get('Tên đầy đủ')),
            'product_type': product_type,
            'bar_code': _parse_text(row.get('Mã vạch')),
            'unit': _parse_text(row.get('ĐVT')),
            'category_name': _parse_text(row.get('Nhóm hàng')),
            'base_price': _parse_decimal(row.get('Giá bán')),
            'description': _parse_text(row.get('Mô tả')),
            'notes': notes,
            'is_active': is_active,
        }
        kv_code = _parse_text(row.get('Mã KiotViet'))
        if kv_code:
            defaults['kiotviet_code'] = kv_code
        # SP sync KV: giữ nguồn; SP mới / tay = nhập tay
        if not (existing and existing.is_kv_synced):
            defaults['sync_source'] = SYNC_SOURCE_MANUAL

        sx_sku = None
        if style and size:
            try:
                sx_sku = get_or_create_sku(
                    style_code=style,
                    color_code=color,
                    size_label=size,
                    color_label=color_label,
                    style_name=name,
                    sku_code=code,
                    user=user,
                )
                code = sx_sku.sku_code
                defaults['color_label'] = sx_sku.color_label or color_label
            except Exception:  # noqa: BLE001
                pass

        if existing:
            for key, value in defaults.items():
                setattr(existing, key, value)
            existing.code = code
            if sx_sku:
                existing.sx_sku = sx_sku
            existing.save()
            updated += 1
        else:
            product = Product(code=code, **defaults)
            if sx_sku:
                product.sx_sku = sx_sku
            if user is not None:
                product.created_by = user
            product.save()
            created += 1

    return {
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:20],
        'error_count': len(errors),
    }
