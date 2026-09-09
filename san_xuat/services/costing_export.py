"""Xuất Excel giá thành kế hoạch (C3/C4)."""

from __future__ import annotations

from io import BytesIO
import re

import pandas as pd
from django.http import HttpResponse
from django.utils import timezone

from san_xuat.hub_models import SxOrderPlanCost
from san_xuat.services.plan_costing import list_active_cost_types


def export_product_costing_xlsx(*, bom, routing=None, result=None, snapshot=None) -> HttpResponse:
    """Xuất Costing hiện tại hoặc một phiên bản Cost đã lưu."""
    from san_xuat.services.costing import compute_costing, costing_details

    if snapshot is not None:
        details = snapshot.details or {}
        material_cost = snapshot.material_cost
        labor_cost = snapshot.labor_cost
        overhead_cost = snapshot.overhead_cost
        other_cost = snapshot.other_cost
        total_cost = snapshot.total_cost
        version_label = snapshot.version_label
        routing = snapshot.routing
        saved_at = timezone.localtime(snapshot.created_at).strftime('%d/%m/%Y %H:%M')
    else:
        result = result or compute_costing(bom, routing=routing)
        details = costing_details(result)
        material_cost = result.material_cost
        labor_cost = result.labor_cost
        overhead_cost = result.overhead_cost
        other_cost = result.other_cost
        total_cost = result.total_cost
        version_label = 'Hiện tại'
        saved_at = ''

    summary_rows = [
        {'Hạng mục': 'Mã sản phẩm', 'Giá trị': bom.tech_doc.product_code},
        {'Hạng mục': 'Tên sản phẩm', 'Giá trị': bom.tech_doc.product_name},
        {'Hạng mục': 'Phiên bản BOM', 'Giá trị': bom.version_label},
        {'Hạng mục': 'Phiên bản OB', 'Giá trị': routing.routing_rev if routing else ''},
        {'Hạng mục': 'Phiên bản Cost', 'Giá trị': version_label},
        {'Hạng mục': 'Thời điểm lưu', 'Giá trị': saved_at},
        {'Hạng mục': 'Chi phí NVL', 'Giá trị': float(material_cost or 0)},
        {'Hạng mục': 'Chi phí nhân công', 'Giá trị': float(labor_cost or 0)},
        {'Hạng mục': 'Chi phí SX chung', 'Giá trị': float(overhead_cost or 0)},
        {'Hạng mục': 'Chi phí khác', 'Giá trị': float(other_cost or 0)},
        {'Hạng mục': 'Tổng giá thành', 'Giá trị': float(total_cost or 0)},
    ]
    material_rows = [
        {
            'Mã NPL': row.get('material_code', ''),
            'Tên NPL': row.get('material_name', ''),
            'Định mức + hao': float(row.get('qty_with_scrap') or 0),
            'ĐVT': row.get('unit_name', ''),
            'Đơn giá BQ': float(row.get('unit_price') or 0),
            'Thành tiền': float(row.get('amount') or 0),
        }
        for row in details.get('material_lines', [])
    ]
    process_rows = []
    for row in details.get('process_lines', []):
        labor_amount = float(row.get('labor_amount') or 0)
        smv_seconds = row.get('smv_seconds')
        if smv_seconds in (None, ''):
            smv_seconds = float(row.get('hours_per_piece') or 0) * 3600
        has_labor_cost = row.get('has_labor_cost')
        if has_labor_cost is None:
            has_labor_cost = labor_amount > 0
        process_rows.append({
            'TT': row.get('sequence', ''),
            'Công đoạn': row.get('process_name', ''),
            'SMV thư viện (giây)': float(row.get('library_smv_seconds') or 0),
            'SMV sản phẩm (giây)': float(smv_seconds or 0),
            'Đơn giá nhân công': labor_amount if has_labor_cost else '',
        })

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name='Tong_hop', index=False)
        pd.DataFrame(material_rows or [{'Thông báo': 'Không có dòng BOM'}]).to_excel(
            writer, sheet_name='BOM', index=False,
        )
        pd.DataFrame(process_rows or [{'Thông báo': 'Không có công đoạn OB'}]).to_excel(
            writer, sheet_name='OB', index=False,
        )
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = 'A2'
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                width = min(max(len(str(cell.value or '')) for cell in column) + 2, 45)
                sheet.column_dimensions[column[0].column_letter].width = width

    output.seek(0)
    safe_code = re.sub(r'[^A-Za-z0-9_-]+', '_', bom.tech_doc.product_code or 'costing')
    safe_version = re.sub(r'[^A-Za-z0-9_-]+', '_', str(version_label or 'current'))
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = (
        f'attachment; filename=Costing_{safe_code}_{safe_version}.xlsx'
    )
    return response


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
