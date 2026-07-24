"""Xuất Excel cho tiện ích."""

from io import BytesIO

import pandas as pd
from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce, NullIf
from django.http import HttpResponse
from django.utils import timezone

from utilities.meal_labels import dish_label_key, merge_counts_by_label, pick_dish_display
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


def export_meal_summary_xlsx(
    meal_date=None,
    *,
    date_from=None,
    date_to=None,
    dish_id: int | None = None,
    dish_label_key_filter: str = '',
) -> HttpResponse:
    if date_from is None and date_to is None and meal_date is not None:
        date_from = date_to = meal_date
    if date_from is None or date_to is None:
        raise ValueError('Cần date_from/date_to hoặc meal_date')
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    qs = MealOrder.objects.filter(
        meal_date__gte=date_from,
        meal_date__lte=date_to,
    )
    if dish_label_key_filter:
        matched_ids = [
            o.pk
            for o in qs.select_related('dish').only('id', 'dish_name', 'dish__name')
            if dish_label_key(o.dish_name or (o.dish.name if o.dish_id else '')) == dish_label_key_filter
        ]
        qs = qs.filter(pk__in=matched_ids)
    elif dish_id:
        qs = qs.filter(dish_id=dish_id)

    rows = []
    for order in qs.select_related(
        'employee__profile', 'employee__profile__department', 'dish',
    ).order_by('meal_date', 'employee__profile__full_name'):
        profile = getattr(order.employee, 'profile', None)
        rows.append({
            'Ngày ăn': order.meal_date.strftime('%d/%m/%Y'),
            'Nhân viên': profile.full_name if profile and profile.full_name else order.employee.username,
            'Phòng ban': profile.department.name if profile and profile.department_id else '',
            'Món': order.display_name(),
            'Ghi chú': order.note,
            'Đặt lúc': timezone.localtime(order.created_at).strftime('%d/%m/%Y %H:%M'),
        })
    labeled = list(
        qs.annotate(label=Coalesce(NullIf('dish_name', Value('')), 'dish__name'))
        .values('meal_date', 'label')
        .annotate(count=Count('id'))
    )
    buckets: dict[tuple, dict] = {}
    for row in labeled:
        key = (row['meal_date'], dish_label_key(row['label']))
        if key not in buckets:
            buckets[key] = {'names': [], 'count': 0}
        buckets[key]['names'].append(row['label'] or '')
        buckets[key]['count'] += row['count']

    if date_from == date_to:
        merged = merge_counts_by_label(
            [{'dish': pick_dish_display(v['names']), 'count': v['count']} for v in buckets.values()],
        )
        totals = [{'Món': row['dish'], 'Số lượng': row['count']} for row in merged]
        empty_totals = [{'Món': '—', 'Số lượng': 0}]
        prefix = f'dat_com_{date_from.isoformat()}'
    else:
        totals = []
        for (meal_dt, _k), data in sorted(buckets.items(), key=lambda x: (x[0][0], -x[1]['count'])):
            totals.append({
                'Ngày ăn': meal_dt.strftime('%d/%m/%Y'),
                'Món': pick_dish_display(data['names']),
                'Số lượng': data['count'],
            })
        empty_totals = [{'Ngày ăn': '—', 'Món': '—', 'Số lượng': 0}]
        prefix = f'dat_com_{date_from.isoformat()}_{date_to.isoformat()}'
    return _xlsx_response(
        {
            'Chi_tiet': pd.DataFrame(rows or [{'Thông báo': 'Chưa có đơn'}]),
            'Tong_mon': pd.DataFrame(totals or empty_totals),
        },
        prefix,
    )


def export_meal_stats_xlsx(stats_rows, *, period_label: str) -> HttpResponse:
    buckets: dict[tuple, dict] = {}
    for r in (stats_rows or []):
        key = (r.get('day') or '', dish_label_key(r.get('dish')))
        if key not in buckets:
            buckets[key] = {'names': [], 'count': 0, 'day': r.get('day') or ''}
        buckets[key]['names'].append(r.get('dish') or '')
        buckets[key]['count'] += int(r.get('count') or 0)
    out_rows = [
        {
            'day': data['day'],
            'dish': pick_dish_display(data['names']),
            'count': data['count'],
        }
        for data in buckets.values()
    ]
    out_rows.sort(key=lambda r: (r['day'], -r['count'], dish_label_key(r['dish'])))
    frame = pd.DataFrame(out_rows or [{'day': '—', 'dish': '—', 'count': 0}])
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
