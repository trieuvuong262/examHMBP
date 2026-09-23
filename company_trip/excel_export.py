from io import BytesIO

import pandas as pd
from django.http import HttpResponse
from django.utils import timezone

from company_trip.constants import STATUS_REGISTERED
from company_trip.models import TripRegistration


def export_registrations_xlsx(qs=None) -> HttpResponse:
    if qs is None:
        qs = TripRegistration.objects.filter(status=STATUS_REGISTERED)
    qs = qs.select_related('profile', 'companion1', 'companion2').order_by('full_name')

    rows = []
    for r in qs:
        rows.append({
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
            'Người thân': r.relative_full_name,
            'CCCD người thân': r.relative_cccd,
            'SĐT người thân': r.relative_phone,
            'Giới tính người thân': {'M': 'Nam', 'F': 'Nữ'}.get(r.relative_gender, r.relative_gender),
            'Ngày sinh người thân': r.relative_date_of_birth.isoformat() if r.relative_date_of_birth else '',
            'Điểm đón': r.pickup_point,
            'Ghi chú': r.note,
            'Trạng thái': r.get_status_display(),
            'Ngày đăng ký': timezone.localtime(r.created_at).strftime('%Y-%m-%d %H:%M') if r.created_at else '',
        })
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
