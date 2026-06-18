"""Xuất Excel cho tiện ích."""

from io import BytesIO

import pandas as pd
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone

from utilities.models import MealOrder, SalaryAdvanceRequest


def _xlsx_response(sheets: dict[str, pd.DataFrame], filename_prefix: str) -> HttpResponse:
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, frame in sheets.items():
            safe_name = sheet_name[:31]
            frame.to_excel(writer, sheet_name=safe_name, index=False)
    output.seek(0)
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename={filename_prefix}_{stamp}.xlsx'
    return response


def export_meal_summary_xlsx(meal_date) -> HttpResponse:
    rows = []
    for order in MealOrder.objects.filter(meal_date=meal_date).select_related(
        'employee__profile', 'dish',
    ).order_by('employee__profile__full_name'):
        profile = getattr(order.employee, 'profile', None)
        rows.append({
            'Ngày ăn': meal_date.strftime('%d/%m/%Y'),
            'Nhân viên': profile.full_name if profile and profile.full_name else order.employee.username,
            'Phòng ban': profile.department.name if profile and profile.department_id else '',
            'Món': order.dish.name,
            'Ghi chú': order.note,
            'Đặt lúc': timezone.localtime(order.created_at).strftime('%d/%m/%Y %H:%M'),
        })
    summary = (
        MealOrder.objects.filter(meal_date=meal_date)
        .values('dish__name')
        .annotate(count=Count('id'))
        .order_by('-count', 'dish__name')
    )
    totals = [{'Món': row['dish__name'], 'Số lượng': row['count']} for row in summary]
    return _xlsx_response(
        {
            'Chi_tiet': pd.DataFrame(rows or [{'Thông báo': 'Chưa có đơn'}]),
            'Tong_mon': pd.DataFrame(totals or [{'Món': '—', 'Số lượng': 0}]),
        },
        f'dat_com_{meal_date.isoformat()}',
    )


def export_meal_stats_xlsx(stats_rows, *, period_label: str) -> HttpResponse:
    frame = pd.DataFrame(stats_rows or [{'day': '—', 'dish': '—', 'count': 0}])
    return _xlsx_response({'Thong_ke': frame}, f'dat_com_thong_ke_{period_label}')


def export_salary_advances_xlsx(qs) -> HttpResponse:
    rows = []
    for item in qs.select_related('employee__profile'):
        profile = getattr(item.employee, 'profile', None)
        rows.append({
            'Tháng': item.request_month.strftime('%m/%Y'),
            'Nhân viên': profile.full_name if profile and profile.full_name else item.employee.username,
            'Phòng ban': profile.department.name if profile and profile.department_id else '',
            'Số tiền': int(item.amount),
            'Ghi chú': item.note,
            'Gửi lúc': timezone.localtime(item.created_at).strftime('%d/%m/%Y %H:%M'),
        })
    return _xlsx_response(
        {'Ung_luong': pd.DataFrame(rows or [{'Thông báo': 'Chưa có yêu cầu'}])},
        'ung_luong',
    )


def export_salary_stats_xlsx(stats_rows) -> HttpResponse:
    frame = pd.DataFrame(stats_rows or [{'month': '—', 'count': 0, 'total': 0}])
    return _xlsx_response({'Thong_ke': frame}, 'ung_luong_thong_ke')
