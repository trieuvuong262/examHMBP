from decimal import Decimal, InvalidOperation

import pandas as pd
from django.http import HttpResponse

from kho_npl.models import Material, MaterialCategory, Supplier, Unit
from kho_npl.services.excel_export import dataframe_to_xlsx_response

EXCEL_HEADERS = [
    'Mã NPL',
    'Tên NPL',
    'Mã nhóm',
    'Màu sắc',
    'Quy cách',
    'Mã ĐVT',
    'Mã NCC',
    'Tồn tối thiểu',
    'Ghi chú',
    'Đang dùng',
]

_HEADER_ALIASES = {
    'ma npl': 'Mã NPL',
    'ma': 'Mã NPL',
    'ten npl': 'Tên NPL',
    'ten': 'Tên NPL',
    'ma nhom': 'Mã nhóm',
    'nhom': 'Mã nhóm',
    'mau sac': 'Màu sắc',
    'mau': 'Màu sắc',
    'quy cach': 'Quy cách',
    'ma dvt': 'Mã ĐVT',
    'dvt': 'Mã ĐVT',
    'ma ncc': 'Mã NCC',
    'ncc': 'Mã NCC',
    'ton toi thieu': 'Tồn tối thiểu',
    'ghi chu': 'Ghi chú',
    'dang dung': 'Đang dùng',
    'trang thai': 'Đang dùng',
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for col in df.columns:
        key = str(col).strip().lower()
        mapping[col] = _HEADER_ALIASES.get(key, str(col).strip())
    return df.rename(columns=mapping)


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


def material_to_row(material: Material) -> dict:
    return {
        'Mã NPL': material.code,
        'Tên NPL': material.name,
        'Mã nhóm': material.category.code,
        'Màu sắc': material.color or '',
        'Quy cách': material.specification or '',
        'Mã ĐVT': material.unit.code,
        'Mã NCC': material.supplier.code if material.supplier_id else '',
        'Tồn tối thiểu': float(material.min_stock),
        'Ghi chú': material.notes or '',
        'Đang dùng': 'Có' if material.is_active else 'Không',
    }


def materials_to_dataframe(qs) -> pd.DataFrame:
    rows = [material_to_row(m) for m in qs]
    if not rows:
        return pd.DataFrame(columns=EXCEL_HEADERS)
    return pd.DataFrame(rows, columns=EXCEL_HEADERS)


def export_materials_xlsx(qs) -> HttpResponse:
    df = materials_to_dataframe(qs.order_by('code'))
    return dataframe_to_xlsx_response(df, 'danh_muc_npl', sheet_name='Danh_muc_NPL')


def sample_template_xlsx() -> HttpResponse:
    sample = pd.DataFrame([{
        'Mã NPL': 'VAI-001',
        'Tên NPL': 'Vải cotton trắng',
        'Mã nhóm': 'vai-chinh',
        'Màu sắc': 'Trắng',
        'Quy cách': '1.5m',
        'Mã ĐVT': 'met',
        'Mã NCC': '',
        'Tồn tối thiểu': 10,
        'Ghi chú': '',
        'Đang dùng': 'Có',
    }], columns=EXCEL_HEADERS)
    return dataframe_to_xlsx_response(sample, 'mau_danh_muc_npl', sheet_name='Mau_NPL')


class MaterialImportError(Exception):
    pass


def import_materials_from_excel(file_obj) -> dict:
    """Import danh mục NPL — tạo mới hoặc cập nhật theo mã."""
    try:
        df = pd.read_excel(file_obj)
    except Exception as exc:
        raise MaterialImportError(f'Không đọc được file Excel: {exc}') from exc

    if df.empty:
        raise MaterialImportError('File Excel không có dữ liệu.')

    df = _normalize_columns(df)
    missing = [h for h in ('Mã NPL', 'Tên NPL', 'Mã nhóm', 'Mã ĐVT') if h not in df.columns]
    if missing:
        raise MaterialImportError(f'Thiếu cột bắt buộc: {", ".join(missing)}')

    categories = {c.code.lower(): c for c in MaterialCategory.objects.all()}
    units = {u.code.lower(): u for u in Unit.objects.all()}
    suppliers = {s.code.lower(): s for s in Supplier.objects.all()}

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for idx, row in df.iterrows():
        line_no = int(idx) + 2
        code = str(row.get('Mã NPL', '')).strip().upper()
        name = str(row.get('Tên NPL', '')).strip()
        cat_code = str(row.get('Mã nhóm', '')).strip().lower()
        unit_code = str(row.get('Mã ĐVT', '')).strip().lower()

        if not code and not name:
            skipped += 1
            continue
        if not code:
            errors.append(f'Dòng {line_no}: thiếu Mã NPL.')
            skipped += 1
            continue
        if not name:
            errors.append(f'Dòng {line_no} ({code}): thiếu Tên NPL.')
            skipped += 1
            continue

        category = categories.get(cat_code)
        if not category:
            errors.append(f'Dòng {line_no} ({code}): không tìm thấy nhóm "{cat_code}".')
            skipped += 1
            continue

        unit = units.get(unit_code)
        if not unit:
            errors.append(f'Dòng {line_no} ({code}): không tìm thấy ĐVT "{unit_code}".')
            skipped += 1
            continue

        supplier = None
        ncc_code = str(row.get('Mã NCC', '')).strip().lower()
        if ncc_code and ncc_code not in ('nan', 'none', ''):
            supplier = suppliers.get(ncc_code)
            if not supplier:
                errors.append(f'Dòng {line_no} ({code}): không tìm thấy NCC "{ncc_code}".')
                skipped += 1
                continue

        defaults = {
            'name': name,
            'category': category,
            'color': str(row.get('Màu sắc', '') or '').strip(),
            'specification': str(row.get('Quy cách', '') or '').strip(),
            'unit': unit,
            'supplier': supplier,
            'min_stock': _parse_decimal(row.get('Tồn tối thiểu')),
            'notes': str(row.get('Ghi chú', '') or '').strip(),
            'is_active': _parse_bool(row.get('Đang dùng')),
        }

        material, is_new = Material.objects.update_or_create(
            code=code,
            defaults=defaults,
        )
        if is_new:
            created += 1
        else:
            updated += 1

    return {
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:20],
        'error_count': len(errors),
    }
