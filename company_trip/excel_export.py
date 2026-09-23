from io import BytesIO

import pandas as pd
from django.http import HttpResponse
from django.utils import timezone

from company_trip.constants import STATUS_REGISTERED
from company_trip.models import TripRegistration


def export_registrations_xlsx(qs=None) -> HttpResponse:
    if qs is None:
        qs = TripRegistration.objects.filter(status=STATUS_REGISTERED)
    qs = qs.select_related('profile', 'companion1', 'companion2').prefetch_related('relatives').order_by('full_name')

    def _gender(code):
        return {'M': 'Nam', 'F': 'Nữ'}.get(code, code or '')

    rows = []
    for r in qs:
        relatives = list(r.relatives.all())
        row = {
            'Họ tên': r.full_name,
            'Email': r.email,
            'SĐT': r.phone,
            'Giới tính': r.gender,
            'Phòng ban': r.department_name,
            'Ngày sinh': r.date_of_birth.isoformat() if r.date_of_birth else '',
            'Loại phòng': r.room_type,
            'Mã phòng': r.room_key,
            'Đồng nghiệp': r.companion1_name,
            'Email đồng nghiệp': r.companion_email,
            'Đồng nghiệp đã xác nhận': 'Có' if r.companion_confirmed else '',
            'Người thân': r.relative_names_display,
            'Điểm đón': r.pickup_point,
            'Ghi chú': r.note,
            'Trạng thái': r.get_status_display(),
            'Ngày đăng ký': timezone.localtime(r.created_at).strftime('%Y-%m-%d %H:%M') if r.created_at else '',
        }
        for index in range(1, 4):
            item = relatives[index - 1] if index - 1 < len(relatives) else None
            row[f'Người thân {index}'] = item.full_name if item else ''
            row[f'CCCD người thân {index}'] = item.cccd if item else ''
            row[f'SĐT người thân {index}'] = item.phone if item else ''
            row[f'Giới tính người thân {index}'] = _gender(item.gender) if item else ''
            row[f'Ngày sinh người thân {index}'] = item.date_of_birth.isoformat() if item and item.date_of_birth else ''
        rows.append(row)
    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='DangKy', index=False)
    output.seek(0)
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename=company_trip_{stamp}.xlsx'
    return response
