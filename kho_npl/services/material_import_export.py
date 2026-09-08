from collections import defaultdict
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.http import HttpResponse

from kho_npl.models import Material, MaterialCategory, MaterialColor, MaterialSpecification, Supplier
from kho_npl.services.excel_export import dataframe_to_xlsx_response, dataframes_to_xlsx_response
from kho_npl.services.material_colors import resolve_material_color
from kho_npl.services.scrap_warehouse import is_usable_storage_location, source_locations_qs

EXCEL_HEADERS = [
    'Mã NPL',
    'Tên NPL',
    'Tên nhóm hàng',
    'Mã nhóm',
    'Màu sắc',
    'Mã quy cách',
    'ĐVT lẻ',
    'Đơn vị chẵn',
    'Mã NCC',
    'Mã vị trí',
    'Tồn tối thiểu',
    'Giá cơ bản',
    'Ghi chú',
    'Đang dùng',
]

_HEADER_ALIASES = {
    'ma npl': 'Mã NPL',
    'ma': 'Mã NPL',
    'ten npl': 'Tên NPL',
    'ten': 'Tên NPL',
    'ten nhom hang': 'Tên nhóm hàng',
    'nhom hang': 'Tên nhóm hàng',
    'ma nhom': 'Mã nhóm',
    'nhom': 'Mã nhóm',
    'mau sac': 'Màu sắc',
    'mau': 'Màu sắc',
    'quy cach': 'Quy cách',
    'quy cách': 'Quy cách',
    'ma quy cach': 'Mã quy cách',
    'mã quy cách': 'Mã quy cách',
    'ma dvt': 'Mã ĐVT',
    'mã đvt': 'Mã ĐVT',
    'dvt': 'Mã ĐVT',
    'đvt': 'Mã ĐVT',
    'dvt le': 'ĐVT lẻ',
    'đvt lẻ': 'ĐVT lẻ',
    'don vi le': 'ĐVT lẻ',
    'đơn vị lẻ': 'ĐVT lẻ',
    'don vi chan': 'Đơn vị chẵn',
    'đơn vị chẵn': 'Đơn vị chẵn',
    'dvt chan': 'Đơn vị chẵn',
    'đvt chẵn': 'Đơn vị chẵn',
    'ma ncc': 'Mã NCC',
    'ncc': 'Mã NCC',
    'ma vi tri': 'Mã vị trí',
    'mã vị trí': 'Mã vị trí',
    'vi tri': 'Mã vị trí',
    'vị trí': 'Mã vị trí',
    'vi tri mac dinh': 'Mã vị trí',
    'vị trí mặc định': 'Mã vị trí',
    'vi tri chinh': 'Mã vị trí',
    'vị trí chính': 'Mã vị trí',
    'ton toi thieu': 'Tồn tối thiểu',
    'gia co ban': 'Giá cơ bản',
    'don gia': 'Giá cơ bản',
    'ghi chu': 'Ghi chú',
    'dang dung': 'Đang dùng',
    'trang thai': 'Đang dùng',
}


def _spec_levels_sorted(specification):
    if specification is None:
        return []
    return sorted(specification.levels.all(), key=lambda row: row.level)


def _spec_base_unit(specification):
    levels = _spec_levels_sorted(specification)
    return levels[0].unit if levels else None


def _spec_package_unit(specification):
    levels = _spec_levels_sorted(specification)
    return levels[-1].unit if len(levels) > 1 else None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for col in df.columns:
        key = str(col).strip().lower()
        mapping[col] = _HEADER_ALIASES.get(key, str(col).strip())
    return df.rename(columns=mapping)


def _parse_text(value) -> str:
    """Chuỗi từ ô Excel — ô trống/NaN trả về '' thay vì 'nan'."""
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


def material_to_row(material: Material) -> dict:
    spec = material.specification if material.specification_id else None
    base_unit = _spec_base_unit(spec) or material.unit
    package_unit = _spec_package_unit(spec)
    return {
        'Mã NPL': material.code,
        'Tên NPL': material.name,
        'Tên nhóm hàng': material.variant_group or '',
        'Mã nhóm': material.category.code,
        'Màu sắc': material.color.name if material.color_id else '',
        'Mã quy cách': spec.code if spec else '',
        'ĐVT lẻ': base_unit.name if base_unit else '',
        'Đơn vị chẵn': package_unit.name if package_unit else '',
        'Mã NCC': material.supplier.code if material.supplier_id else '',
        'Mã vị trí': material.primary_location.code if material.primary_location_id else '',
        'Tồn tối thiểu': float(material.min_stock),
        'Giá cơ bản': float(material.base_price),
        'Ghi chú': material.notes or '',
        'Đang dùng': 'Có' if material.is_active else 'Không',
    }


def materials_to_dataframe(qs) -> pd.DataFrame:
    rows = [material_to_row(m) for m in qs]
    if not rows:
        return pd.DataFrame(columns=EXCEL_HEADERS)
    return pd.DataFrame(rows, columns=EXCEL_HEADERS)


def export_materials_xlsx(qs) -> HttpResponse:
    df = materials_to_dataframe(
        qs.select_related('primary_location', 'specification', 'unit')
        .prefetch_related('specification__levels__unit')
        .order_by('code')
    )
    return dataframe_to_xlsx_response(df, 'danh_muc_npl', sheet_name='Danh_muc_NPL')


def _specification_catalog_rows():
    rows = []
    specs = (
        MaterialSpecification.objects.filter(is_active=True)
        .prefetch_related('levels__unit')
        .order_by('sort_order', 'name')
    )
    for spec in specs:
        base = _spec_base_unit(spec)
        package = _spec_package_unit(spec)
        if not base:
            continue
        rows.append({
            'Mã quy cách': spec.code,
            'Tên quy cách': spec.name,
            'Công thức': spec.conversion_formula,
            'ĐVT lẻ': base.name if base else '',
            'Đơn vị chẵn': package.name if package else '',
        })
    return rows


def sample_template_xlsx() -> HttpResponse:
    sample_category = MaterialCategory.objects.filter(is_active=True).order_by('sort_order', 'name').first()
    sample_location = source_locations_qs().order_by('code').first()
    sample_spec = (
        MaterialSpecification.objects.filter(is_active=True, levels__level=1)
        .prefetch_related('levels__unit')
        .order_by('sort_order', 'name')
        .first()
    )
    base = _spec_base_unit(sample_spec)
    package = _spec_package_unit(sample_spec)
    sample = pd.DataFrame([{
        'Mã NPL': 'VAI-001',
        'Tên NPL': 'Vải cotton trắng',
        'Tên nhóm hàng': 'COTTON',
        'Mã nhóm': sample_category.code if sample_category else '',
        'Màu sắc': 'Trắng',
        'Mã quy cách': sample_spec.code if sample_spec else '',
        'ĐVT lẻ': base.name if base else '',
        'Đơn vị chẵn': package.name if package else '',
        'Mã NCC': '',
        'Mã vị trí': sample_location.code if sample_location else '',
        'Tồn tối thiểu': 10,
        'Giá cơ bản': 15000,
        'Ghi chú': 'Tồn tối thiểu và giá cơ bản theo ĐVT lẻ',
        'Đang dùng': 'Có',
    }], columns=EXCEL_HEADERS)
    spec_rows = _specification_catalog_rows()
    spec_df = pd.DataFrame(spec_rows) if spec_rows else pd.DataFrame(
        columns=['Mã quy cách', 'Tên quy cách', 'Công thức', 'ĐVT lẻ', 'Đơn vị chẵn']
    )
    return dataframes_to_xlsx_response(
        {'Mau_NPL': sample, 'Quy_cach': spec_df},
        'mau_danh_muc_npl',
    )


class MaterialImportError(Exception):
    pass


def _unique_specs(specs):
    return list({spec.pk: spec for spec in specs}.values())


def _pick_spec_for_unit(unit_key: str, specs_by_unit):
    candidates = _unique_specs(specs_by_unit.get(unit_key, []))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    coded = [
        spec for spec in candidates
        if spec.code.lower() in {f'dvt-{unit_key}', unit_key}
    ]
    if len(coded) == 1:
        return coded[0]
    one_level = [spec for spec in candidates if len(_spec_levels_sorted(spec)) == 1]
    if len(one_level) == 1:
        return one_level[0]
    return None


def _resolve_row_specification(row, specs_by_code, specs_by_name, specs_by_unit, existing=None):
    spec_code = _parse_text(row.get('Mã quy cách')).lower()
    legacy_spec = _parse_text(row.get('Quy cách')).lower()
    unit_key = (
        _parse_text(row.get('Mã ĐVT'))
        or _parse_text(row.get('ĐVT lẻ'))
    ).lower()

    specification = specs_by_code.get(spec_code) if spec_code else None
    # File cũ: cột Quy cách thường là chữ tự do, Mã ĐVT mới là ĐVT lẻ thật.
    # Khi cập nhật NPL đã có quy cách nhiều cấp, giữ nguyên nếu ĐVT lẻ còn khớp.
    if specification is None and unit_key and existing and existing.specification_id:
        existing_base = _spec_base_unit(existing.specification)
        if existing_base and unit_key in {
            existing_base.code.lower(),
            existing_base.name.strip().lower(),
        }:
            specification = existing.specification
    if specification is None and unit_key:
        specification = _pick_spec_for_unit(unit_key, specs_by_unit)
    if specification is None and legacy_spec:
        specification = specs_by_code.get(legacy_spec) or specs_by_name.get(legacy_spec)

    requested = spec_code or unit_key or legacy_spec
    return specification, requested, unit_key


def import_materials_from_excel(file_obj) -> dict:
    """Import danh mục NPL — tạo mới hoặc cập nhật theo mã."""
    try:
        df = pd.read_excel(file_obj)
    except Exception as exc:
        raise MaterialImportError(f'Không đọc được file Excel: {exc}') from exc

    if df.empty:
        raise MaterialImportError('File Excel không có dữ liệu.')

    df = _normalize_columns(df)
    missing = [h for h in ('Mã NPL', 'Tên NPL', 'Mã nhóm') if h not in df.columns]
    has_spec_hint = any(
        col in df.columns for col in ('Mã quy cách', 'Quy cách', 'Mã ĐVT', 'ĐVT lẻ')
    )
    if not has_spec_hint:
        missing.append('Mã quy cách')
    if missing:
        raise MaterialImportError(f'Thiếu cột bắt buộc: {", ".join(missing)}')

    categories = {c.code.lower(): c for c in MaterialCategory.objects.all()}
    suppliers = {s.code.lower(): s for s in Supplier.objects.all()}
    locations_by_code = {loc.code.lower(): loc for loc in source_locations_qs()}
    locations_by_name = {loc.name.strip().lower(): loc for loc in source_locations_qs() if (loc.name or '').strip()}
    colors_by_name = {c.name.lower(): c for c in MaterialColor.objects.filter(is_active=True)}
    specs = list(
        MaterialSpecification.objects.filter(is_active=True).prefetch_related('levels__unit')
    )
    specs_by_code = {s.code.lower(): s for s in specs}
    specs_by_name = {s.name.strip().lower(): s for s in specs if (s.name or '').strip()}
    specs_by_unit = defaultdict(list)
    for spec in specs:
        base = _spec_base_unit(spec)
        if not base:
            continue
        specs_by_unit[base.code.lower()].append(spec)
        specs_by_unit[base.name.strip().lower()].append(spec)

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for idx, row in df.iterrows():
        line_no = int(idx) + 2
        code = str(row.get('Mã NPL', '')).strip().upper()
        name = str(row.get('Tên NPL', '')).strip()
        cat_code = str(row.get('Mã nhóm', '')).strip().lower()

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

        supplier = None
        ncc_code = str(row.get('Mã NCC', '')).strip().lower()
        if ncc_code and ncc_code not in ('nan', 'none', ''):
            supplier = suppliers.get(ncc_code)
            if not supplier:
                errors.append(f'Dòng {line_no} ({code}): không tìm thấy NCC "{ncc_code}".')
                skipped += 1
                continue

        location = None
        has_location_col = 'Mã vị trí' in df.columns
        if has_location_col:
            loc_raw = str(row.get('Mã vị trí', '') or '').strip()
            if loc_raw and loc_raw.lower() not in ('nan', 'none'):
                location = locations_by_code.get(loc_raw.lower()) or locations_by_name.get(loc_raw.lower())
                if not location or not is_usable_storage_location(location):
                    errors.append(f'Dòng {line_no} ({code}): không tìm thấy vị trí "{loc_raw}".')
                    skipped += 1
                    continue

        color = None
        color_name = str(row.get('Màu sắc', '') or '').strip()
        if color_name and color_name.lower() not in ('nan', 'none'):
            color = colors_by_name.get(color_name.lower()) or resolve_material_color(color_name)
            if not color:
                errors.append(f'Dòng {line_no} ({code}): không tìm thấy màu "{color_name}".')
                skipped += 1
                continue

        existing = (
            Material.objects.select_related('specification')
            .prefetch_related('specification__levels__unit')
            .filter(code=code)
            .first()
        )
        specification, requested_spec, unit_key = _resolve_row_specification(
            row, specs_by_code, specs_by_name, specs_by_unit, existing=existing,
        )
        base_level_unit = _spec_base_unit(specification)
        if not specification or not base_level_unit:
            errors.append(
                f'Dòng {line_no} ({code}): không tìm thấy quy cách hợp lệ "{requested_spec}".'
            )
            skipped += 1
            continue
        if unit_key and unit_key not in {
            base_level_unit.code.lower(),
            base_level_unit.name.strip().lower(),
        }:
            errors.append(
                f'Dòng {line_no} ({code}): ĐVT "{unit_key}" không khớp ĐVT lẻ '
                f'của quy cách {specification.code} ({base_level_unit.name}).'
            )
            skipped += 1
            continue

        defaults = {
            'name': name,
            'variant_group': str(row.get('Tên nhóm hàng', '') or '').strip().upper(),
            'category': category,
            'color': color,
            'specification': specification,
            'unit': base_level_unit,
            'supplier': supplier,
            'min_stock': _parse_decimal(row.get('Tồn tối thiểu')),
            'base_price': _parse_decimal(row.get('Giá cơ bản')),
            'notes': _parse_text(row.get('Ghi chú')),
            'is_active': _parse_bool(row.get('Đang dùng')),
        }
        if has_location_col:
            defaults['primary_location'] = location

        if not defaults['variant_group'] or defaults['variant_group'].lower() in ('nan', 'none'):
            from kho_npl.variant_group import infer_variant_group_from_code
            defaults['variant_group'] = infer_variant_group_from_code(code)

        if existing and existing.unit_id != base_level_unit.pk:
            has_stock = (
                existing.balances.filter(quantity__gt=0).exists()
                or existing.batches.filter(quantity__gt=0).exists()
            )
            if has_stock:
                errors.append(
                    f'Dòng {line_no} ({code}): không thể đổi ĐVT lẻ khi NPL còn tồn.'
                )
                skipped += 1
                continue

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
