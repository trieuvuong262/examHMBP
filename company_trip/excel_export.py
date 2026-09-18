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
            'Cùng phòng 1': r.companion1_name,
            'Cùng phòng 2': r.companion2_name,
            'Ăn chay': r.vegetarian,
            'Dị ứng': r.allergy_note,
            'Điểm đón': r.pickup_point,
            'Ăn sáng': r.breakfast_choice,
            'Lộ trình': r.route,
            'Mua sắm': r.shopping,
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
