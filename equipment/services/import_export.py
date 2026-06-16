"""Import / export thiết bị theo loại."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
from django.db.models import Q

from equipment.categories import (
    IMPORT_COLUMNS_IT,
    IMPORT_COLUMNS_MACHINE,
    import_columns_for_category,
    sample_row_for_category,
)
from equipment.scope import SCOPE_PRODUCTION
from equipment.services.device_categories import (
    category_map,
    normalize_category_value,
)
from equipment.models import Device


def export_columns_for_scope(equipment_scope: str | None) -> list[tuple[str, str]]:
    """
    Cột xuất Excel khớp mẫu nhập theo phạm vi IT / sản xuất (+ vài cột tra cứu).
    """
    if equipment_scope == SCOPE_PRODUCTION:
        import_cols = IMPORT_COLUMNS_MACHINE
    else:
        import_cols = IMPORT_COLUMNS_IT

    cols: list[tuple[str, str]] = [(key, label) for key, label, _required in import_cols]

    name_idx = next(i for i, (key, _label) in enumerate(cols) if key == 'name')
    cols[name_idx + 1:name_idx + 1] = [
        ('category', 'Loại (mã)'),
        ('category_label', 'Loại thiết bị'),
    ]

    status_idx = next(i for i, (key, _label) in enumerate(cols) if key == 'status')
    cols.insert(status_idx + 1, ('status_label', 'Trạng thái (hiển thị)'))

    if equipment_scope == SCOPE_PRODUCTION:
        desc_idx = next(i for i, (key, _label) in enumerate(cols) if key == 'description')
        cols.insert(desc_idx + 1, ('configuration', 'Thông số kỹ thuật'))
        cols.extend([
            ('total_price', 'Thành tiền (VNĐ)'),
        ])
    else:
        cols.extend([
            ('windows_version', 'Phiên bản Windows'),
            ('windows_license', 'License Windows'),
        ])

    cols.extend([
        ('created_at', 'Ngày tạo'),
        ('updated_at', 'Cập nhật lần cuối'),
    ])
    return cols


def export_sheet_title_for_scope(equipment_scope: str | None) -> str:
    return 'Thiết bị sản xuất' if equipment_scope == SCOPE_PRODUCTION else 'Thiết bị IT'

def status_map() -> dict[str, str]:
    from equipment.services.device_statuses import status_map as _status_map
    return _status_map()


STATUS_MAP = status_map()

# Alias cột Excel (tiếng Việt / tên cũ)
COLUMN_ALIASES = {
    'device_code': ('device_code', 'Mã thiết bị', 'ma thiet bi'),
    'name': ('name', 'Tên thiết bị', 'ten thiet bi'),
    'managed_department': (
        'managed_department', 'managed_department_label', 'managed_by', 'Bộ phận quản lý', 'bo phan quan ly',
    ),
    'status': ('status', 'Trạng thái', 'trang thai'),
    'usage_department_text': (
        'usage_department_text', 'usage_department', 'Phòng ban sử dụng', 'phong ban su dung',
    ),
    'usage_room': ('usage_room', 'Phòng / vị trí', 'phong / vi tri', 'vi tri'),
    'assigned_user_text': ('assigned_user_text', 'user', 'Người dùng', 'nguoi dung'),
    'contact_email': ('contact_email', 'Email liên hệ', 'email'),
    'handover_date': ('handover_date', 'Ngày bàn giao', 'ngay ban giao'),
    'model_number': ('model_number', 'Model', 'model'),
    'serial_number': ('serial_number', 'Serial Number', 'serial'),
    'configuration': ('configuration', 'Cấu hình', 'cau hinh'),
    'description': ('description', 'Mô tả', 'mo ta'),
    'hostname': ('hostname', 'Hostname'),
    'ip_address': ('ip_address', 'Địa chỉ IP', 'dia chi ip', 'ip'),
    'quantity': ('quantity', 'Số lượng', 'so luong'),
    'unit_price': ('unit_price', 'Đơn giá', 'don gia'),
}


def _parse_excel_date(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, 'date'):
        return value.date()
    text = str(value).strip()
    if not text or text.lower() == 'nat':
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _cell(row, field_key, default=None):
    keys = COLUMN_ALIASES.get(field_key, (field_key,))
    for key in keys:
        if key in row.index:
            val = row.get(key)
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return val
    return default


def _safe_str(value, default=''):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip()


def _safe_int(value, default=0):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def build_sample_dataframe(category_code: str) -> pd.DataFrame:
    """Tạo DataFrame mẫu cho loại thiết bị."""
    columns = import_columns_for_category(category_code)
    row = sample_row_for_category(category_code)
    data = {}
    for field_key, header, _required in columns:
        data[header] = [row.get(field_key, '')]
    return pd.DataFrame(data)


def apply_device_list_filters(qs, params):
    """Áp dụng bộ lọc giống trang danh sách thiết bị."""
    q = (params.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(device_code__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(model_number__icontains=q)
            | Q(hostname__icontains=q)
            | Q(ip_address__icontains=q)
            | Q(usage_department_text__icontains=q)
            | Q(assigned_user_text__icontains=q)
            | Q(usage_department__name__icontains=q)
        )

    managed_department = params.get('managed_department')
    if managed_department:
        qs = qs.filter(managed_department_id=managed_department)

    categories = params.getlist('category') if hasattr(params, 'getlist') else []
    if not categories and params.get('category'):
        categories = [params.get('category')]
    if categories:
        qs = qs.filter(category__in=categories)

    status = params.get('status')
    if status:
        qs = qs.filter(status=status)

    usage_department = params.get('usage_department')
    if usage_department:
        qs = qs.filter(
            Q(usage_department_text=usage_department)
            | Q(usage_department__name=usage_department)
        )

    usage_room = (params.get('usage_room') or '').strip()
    if usage_room:
        qs = qs.filter(usage_room__icontains=usage_room)

    device_ids = params.getlist('device_ids') if hasattr(params, 'getlist') else []
    if device_ids:
        qs = qs.filter(id__in=device_ids)

    return qs.order_by('-created_at')


def _device_export_row(device) -> dict:
    managed_label = ''
    if device.managed_department_id:
        managed_label = device.managed_department_label
    return {
        'device_code': device.device_code,
        'name': device.name,
        'category': device.category,
        'category_label': category_map().get(device.category, device.category),
        'managed_department': managed_label,
        'managed_department_label': managed_label,
        'status': device.status,
        'status_label': STATUS_MAP.get(device.status, device.status),
        'usage_department_text': device.usage_department_text or (
            device.usage_department.name if device.usage_department_id else ''
        ),
        'usage_room': device.usage_room,
        'assigned_user_text': device.assigned_user_text or device.assigned_user_label,
        'contact_email': device.contact_email,
        'handover_date': device.handover_date.isoformat() if device.handover_date else '',
        'model_number': device.model_number,
        'serial_number': device.serial_number,
        'configuration': device.configuration,
        'description': device.description,
        'hostname': device.hostname,
        'ip_address': str(device.ip_address) if device.ip_address else '',
        'windows_version': device.windows_version,
        'windows_license': device.windows_license,
        'quantity': device.quantity,
        'unit_price': int(device.unit_price or 0),
        'total_price': int(device.total_price or 0),
        'created_at': device.created_at.strftime('%Y-%m-%d %H:%M') if device.created_at else '',
        'updated_at': device.updated_at.strftime('%Y-%m-%d %H:%M') if device.updated_at else '',
    }


def devices_to_dataframe(devices, equipment_scope: str | None = None) -> pd.DataFrame:
    export_cols = export_columns_for_scope(equipment_scope)
    col_keys = [key for key, _label in export_cols]
    col_labels = [label for _key, label in export_cols]

    rows = [_device_export_row(d) for d in devices]
    if not rows:
        return pd.DataFrame(columns=col_labels)

    df = pd.DataFrame(rows)
    ordered = [key for key in col_keys if key in df.columns]
    rename = {key: label for key, label in export_cols}
    return df[ordered].rename(columns=rename)


def count_for_export(params) -> int:
    return apply_device_list_filters(Device.objects.all(), params).count()


def build_export_filename(
    count: int,
    equipment_scope: str | None = None,
    category_codes: list[str] | None = None,
) -> str:
    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    scope_slug = 'san_xuat' if equipment_scope == SCOPE_PRODUCTION else 'IT'
    if category_codes and len(category_codes) == 1:
        code = category_codes[0]
        label = category_map().get(code, code).replace('/', '-').replace(' ', '_')[:20]
        return f'thiet_bi_{scope_slug}_{label}_{count}_{stamp}.xlsx'
    return f'thiet_bi_{scope_slug}_{count}_{stamp}.xlsx'


def export_devices_excel(queryset, equipment_scope: str | None = None) -> BytesIO:
    df = devices_to_dataframe(queryset, equipment_scope=equipment_scope)
    buffer = BytesIO()
    sheet_name = export_sheet_title_for_scope(equipment_scope)[:31]
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        worksheet = writer.sheets[sheet_name]
        for column_cells in worksheet.columns:
            letter = column_cells[0].column_letter
            max_length = 0
            for cell in column_cells:
                value = cell.value
                if value is not None:
                    max_length = max(max_length, len(str(value)))
            worksheet.column_dimensions[letter].width = min(max(max_length + 2, 10), 42)
    buffer.seek(0)
    return buffer


def import_devices_from_excel(file_obj, category_code: str) -> tuple[int, list[str]]:
    """
    Nhập thiết bị từ Excel theo loại đã chọn.
    Trả về (số bản ghi thành công, danh sách lỗi).
    """
    if category_code not in category_map():
        return 0, [f'Loại thiết bị không hợp lệ: {category_code}']

    df = pd.read_excel(file_obj)
    df = df.replace({pd.NA: None})
    if df.empty:
        return 0, ['File Excel không có dữ liệu.']

    from equipment.services.device_categories import import_profile_for_code
    from equipment.services.managed_department import default_managed_department_for_scope, resolve_managed_department

    count = 0
    errors = []
    default_scope = 'it' if import_profile_for_code(category_code) == 'it' else 'production'
    default_dept = default_managed_department_for_scope(default_scope)

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # header = dòng 1
        name = _cell(row, 'name')
        if not name:
            continue

        file_category = _cell(row, 'category') or _cell(row, 'Loại')
        if file_category:
            normalized = normalize_category_value(file_category)
            if normalized and normalized != category_code:
                errors.append(
                    f'Dòng {row_num}: loại trong file ({file_category}) khác loại đã chọn ({category_code}).'
                )
                continue

        ip_raw = _cell(row, 'ip_address')
        ip_value = None
        if ip_raw is not None and str(ip_raw).strip():
            ip_value = str(ip_raw).strip()

        try:
            from equipment.services.device_code import normalize_device_code
            from equipment.services.device_statuses import normalize_status_value

            device_code_raw = normalize_device_code(_cell(row, 'device_code'))
            managed_raw = _cell(row, 'managed_department') or _cell(row, 'managed_by')
            managed_dept = resolve_managed_department(managed_raw) or default_dept
            status_raw = _safe_str(_cell(row, 'status'), Device.STATUS_NEW) or Device.STATUS_NEW
            status_value = normalize_status_value(status_raw) or status_raw
            Device.objects.create(
                device_code=device_code_raw,
                name=_safe_str(name),
                category=category_code,
                managed_department=managed_dept,
                status=status_value,
                usage_department_text=_safe_str(_cell(row, 'usage_department_text')),
                usage_room=_safe_str(_cell(row, 'usage_room')),
                assigned_user_text=_safe_str(_cell(row, 'assigned_user_text')),
                contact_email=_safe_str(_cell(row, 'contact_email')),
                handover_date=_parse_excel_date(_cell(row, 'handover_date')),
                model_number=_safe_str(_cell(row, 'model_number')),
                serial_number=_safe_str(_cell(row, 'serial_number')),
                configuration=_safe_str(_cell(row, 'configuration')),
                description=_safe_str(_cell(row, 'description')),
                hostname=_safe_str(_cell(row, 'hostname')),
                ip_address=ip_value,
                quantity=max(1, _safe_int(_cell(row, 'quantity'), 1)),
                unit_price=_safe_int(_cell(row, 'unit_price'), 0),
            )
            count += 1
        except Exception as exc:
            errors.append(f'Dòng {row_num}: {exc}')

    return count, errors
