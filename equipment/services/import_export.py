"""Import / export thiết bị theo loại."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
from django.db.models import Q

from equipment.categories import import_columns_for_category, sample_row_for_category
from equipment.services.device_categories import (
    category_map,
    normalize_category_value,
)
from equipment.models import Device


# Cột export (mã DB → tiêu đề Excel)
EXPORT_COLUMNS = [
    ('name', 'Tên thiết bị'),
    ('category', 'Loại (mã)'),
    ('category_label', 'Loại thiết bị'),
    ('managed_by', 'Bộ phận QL (mã)'),
    ('managed_by_label', 'Bộ phận quản lý'),
    ('status', 'Trạng thái (mã)'),
    ('status_label', 'Trạng thái'),
    ('usage_department_text', 'Phòng ban sử dụng'),
    ('usage_room', 'Phòng / vị trí'),
    ('assigned_user_text', 'Người dùng'),
    ('contact_email', 'Email liên hệ'),
    ('handover_date', 'Ngày bàn giao'),
    ('model_number', 'Model'),
    ('serial_number', 'Serial Number'),
    ('configuration', 'Cấu hình'),
    ('description', 'Mô tả'),
    ('hostname', 'Hostname'),
    ('ip_address', 'Địa chỉ IP'),
    ('is_online', 'Trạng thái mạng'),
    ('quantity', 'Số lượng'),
    ('unit_price', 'Đơn giá'),
    ('total_price', 'Thành tiền'),
    ('created_at', 'Ngày tạo'),
    ('updated_at', 'Cập nhật lần cuối'),
]

MANAGED_MAP = dict(Device.MANAGED_CHOICES)
STATUS_MAP = dict(Device.STATUS_CHOICES)

# Alias cột Excel (tiếng Việt / tên cũ)
COLUMN_ALIASES = {
    'name': ('name', 'Tên thiết bị', 'ten thiet bi'),
    'managed_by': ('managed_by', 'Bộ phận QL', 'bo phan ql'),
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
            | Q(serial_number__icontains=q)
            | Q(model_number__icontains=q)
            | Q(hostname__icontains=q)
            | Q(ip_address__icontains=q)
            | Q(usage_department_text__icontains=q)
            | Q(assigned_user_text__icontains=q)
            | Q(usage_department__name__icontains=q)
        )

    managed_by = params.get('managed_by')
    if managed_by:
        qs = qs.filter(managed_by=managed_by)

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

    is_online = params.get('is_online')
    if is_online == '1':
        qs = qs.filter(is_online=True)
    elif is_online == '0':
        qs = qs.filter(is_online=False)

    device_ids = params.getlist('device_ids') if hasattr(params, 'getlist') else []
    if device_ids:
        qs = qs.filter(id__in=device_ids)

    return qs.order_by('-created_at')


def devices_to_dataframe(devices) -> pd.DataFrame:
    rows = []
    for d in devices:
        rows.append({
            'name': d.name,
            'category': d.category,
            'category_label': category_map().get(d.category, d.category),
            'managed_by': d.managed_by,
            'managed_by_label': MANAGED_MAP.get(d.managed_by, d.managed_by),
            'status': d.status,
            'status_label': STATUS_MAP.get(d.status, d.status),
            'usage_department_text': d.usage_department_text or (
                d.usage_department.name if d.usage_department_id else ''
            ),
            'usage_room': d.usage_room,
            'assigned_user_text': d.assigned_user_text or d.assigned_user_label,
            'contact_email': d.contact_email,
            'handover_date': d.handover_date.isoformat() if d.handover_date else '',
            'model_number': d.model_number,
            'serial_number': d.serial_number,
            'configuration': d.configuration,
            'description': d.description,
            'hostname': d.hostname,
            'ip_address': str(d.ip_address) if d.ip_address else '',
            'is_online': 'Online' if d.is_online else 'Offline',
            'quantity': d.quantity,
            'unit_price': int(d.unit_price or 0),
            'total_price': int(d.total_price or 0),
            'created_at': d.created_at.strftime('%Y-%m-%d %H:%M') if d.created_at else '',
            'updated_at': d.updated_at.strftime('%Y-%m-%d %H:%M') if d.updated_at else '',
        })
    if not rows:
        return pd.DataFrame(columns=[label for _key, label in EXPORT_COLUMNS])
    df = pd.DataFrame(rows)
    rename = {key: label for key, label in EXPORT_COLUMNS}
    return df[[key for key, _label in EXPORT_COLUMNS if key in df.columns]].rename(columns=rename)


def count_for_export(params) -> int:
    return apply_device_list_filters(Device.objects.all(), params).count()


def build_export_filename(count: int, category_codes: list[str] | None = None) -> str:
    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    if category_codes and len(category_codes) == 1:
        code = category_codes[0]
        label = category_map().get(code, code).replace('/', '-').replace(' ', '_')[:20]
        return f'thiet_bi_{label}_{count}_{stamp}.xlsx'
    return f'thiet_bi_justplay_{count}_{stamp}.xlsx'


def export_devices_excel(queryset) -> BytesIO:
    df = devices_to_dataframe(queryset)
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')
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

    count = 0
    errors = []
    default_managed = (
        Device.MANAGED_IT if category_code in ('PC', 'Laptop', 'Printer', 'Network', 'Internet', 'CCTV', 'PHONE', 'ATTENDANCE', 'DISPLAY')
        else Device.MANAGED_MAINTENANCE
    )

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
            Device.objects.create(
                name=_safe_str(name),
                category=category_code,
                managed_by=_safe_str(_cell(row, 'managed_by'), default_managed) or default_managed,
                status=_safe_str(_cell(row, 'status'), Device.STATUS_NEW) or Device.STATUS_NEW,
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
