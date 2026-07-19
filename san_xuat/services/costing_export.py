"""Xuất Excel giá thành kế hoạch (C3/C4)."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from django.http import HttpResponse
from django.utils import timezone

from san_xuat.hub_models import SxOrderPlanCost
from san_xuat.services.plan_costing import list_active_cost_types


def export_order_plan_cost_xlsx(*, sheet: SxOrderPlanCost) -> HttpResponse:
    cost_types = list_active_cost_types()
    header_rows = [{
        'Mã bảng': sheet.code,
        'Tên': sheet.name,
        'Đơn KV': sheet.kv_order_code,
        'Kỳ từ': sheet.date_from.strftime('%d/%m/%Y'),
        'Kỳ đến': sheet.date_to.strftime('%d/%m/%Y'),
        'Trạng thái': sheet.get_status_display(),
        'Tổng GTKH': float(sheet.total_cost or 0),
    }]
    line_rows = []
    lines = sheet.lines.prefetch_related('typed_extras__cost_type').all()
    for line in lines:
        amounts = {
            ex.cost_type_id: float(ex.amount or 0)
            for ex in line.typed_extras.all()
        }
        row = {
            'Mã SP': line.product_code,
            'Tên SP': line.product_name,
            'SL': float(line.qty or 0),
            'GT/cái': float(line.unit_cost or 0),
        }
        for ct in cost_types:
            row[ct.name] = amounts.get(ct.pk, 0.0)
        row['CP thêm (tổng)'] = float(line.extra_cost or 0)
        row['Thành tiền'] = float(line.line_cost or 0)
        line_rows.append(row)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(header_rows).to_excel(writer, sheet_name='Tong_hop', index=False)
        pd.DataFrame(line_rows or [{'Thông báo': 'Không có dòng'}]).to_excel(
            writer, sheet_name='Chi_tiet', index=False,
        )
    output.seek(0)
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename={sheet.code}_{stamp}.xlsx'
    return response
