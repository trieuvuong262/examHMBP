from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_POSTED, STOCK_STATUS_LOW, STOCK_STATUS_OUT
from kho_npl.models import StockIssue, StockIssueLine, StockLedger, Stocktake, StocktakeLine
from kho_npl.services.stock import material_stock_rows


def _parse_date(value: str | None, default: date | None = None) -> date | None:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return default


def report_stock_current_rows():
    rows = []
    for row in material_stock_rows():
        m = row['material']
        rows.append({
            'Mã NPL': m.code,
            'Tên': m.name,
            'Nhóm': m.category.name,
            'ĐVT': m.unit.name,
            'Tồn': float(row['total_qty']),
            'Tối thiểu': float(m.min_stock),
            'Trạng thái': row['status_label'],
            'Vị trí chính': row['primary_location'],
        })
    return rows


def report_alert_rows():
    rows = []
    for row in material_stock_rows():
        if row['status'] not in (STOCK_STATUS_LOW, STOCK_STATUS_OUT):
            continue
        m = row['material']
        rows.append({
            'Mã NPL': m.code,
            'Tên': m.name,
            'Nhóm': m.category.name,
            'Tồn': float(row['total_qty']),
            'Tối thiểu': float(m.min_stock),
            'Trạng thái': row['status_label'],
        })
    return rows


def report_movement_rows(date_from: date | None, date_to: date | None, material_code: str = ''):
    qs = StockLedger.objects.select_related('material', 'location', 'created_by').order_by('-created_at')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if material_code:
        qs = qs.filter(material__code__icontains=material_code.strip())
    rows = []
    ref_labels = {
        StockLedger.REF_RECEIPT: 'Nhập',
        StockLedger.REF_ISSUE: 'Xuất',
        StockLedger.REF_ADJUSTMENT: 'Điều chỉnh',
        StockLedger.REF_STOCKTAKE: 'Kiểm kê',
    }
    for entry in qs[:5000]:
        rows.append({
            'Thời gian': timezone.localtime(entry.created_at).strftime('%d/%m/%Y %H:%M'),
            'Mã NPL': entry.material.code,
            'Tên NPL': entry.material.name,
            'Vị trí': entry.location.code,
            'Loại': ref_labels.get(entry.ref_type, entry.ref_type),
            'Số chứng từ': entry.ref_number,
            'Biến động': float(entry.qty_delta),
            'Tồn sau': float(entry.balance_after),
            'Người thực hiện': (
                entry.created_by.get_full_name() or entry.created_by.username
            ) if entry.created_by else '',
        })
    return rows


def report_issue_by_lsx_rows(date_from: date | None, date_to: date | None, lsx: str = ''):
    qs = StockIssueLine.objects.select_related(
        'issue', 'material', 'location',
    ).filter(issue__status=DOC_STATUS_POSTED)
    if date_from:
        qs = qs.filter(issue__issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue__issue_date__lte=date_to)
    if lsx:
        qs = qs.filter(
            Q(issue__production_order__icontains=lsx) | Q(issue__product_code__icontains=lsx),
        )
    rows = []
    for line in qs.order_by('-issue__issue_date')[:5000]:
        rows.append({
            'Ngày xuất': line.issue.issue_date.strftime('%d/%m/%Y'),
            'Số phiếu': line.issue.number,
            'LSX': line.issue.production_order,
            'Mã SP': line.issue.product_code,
            'Lý do': line.issue.get_issue_type_display(),
            'Mã NPL': line.material.code,
            'Tên NPL': line.material.name,
            'Vị trí': line.location.code,
            'Số lượng': float(line.quantity),
        })
    return rows


def report_stocktake_history_rows():
    rows = []
    for st in Stocktake.objects.filter(status='closed').order_by('-stocktake_date')[:200]:
        lines = st.lines.all()
        variance_total = sum(
            (line.actual_qty or Decimal('0')) - line.system_qty for line in lines
        )
        diff_count = sum(
            1 for line in lines
            if line.actual_qty is not None and line.actual_qty != line.system_qty
        )
        rows.append({
            'Mã kỳ': st.number,
            'Tên kỳ': st.name,
            'Ngày kiểm': st.stocktake_date.strftime('%d/%m/%Y'),
            'Số dòng': lines.count(),
            'Dòng chênh': diff_count,
            'Tổng chênh': float(variance_total),
            'Ngày chốt': timezone.localtime(st.closed_at).strftime('%d/%m/%Y %H:%M') if st.closed_at else '',
        })
    return rows


def report_ledger_detail_rows(date_from: date | None, date_to: date | None, material_code: str = ''):
    return report_movement_rows(date_from, date_to, material_code)


def stocktake_variance_detail(stocktake_id: int):
    rows = []
    for line in StocktakeLine.objects.filter(
        stocktake_id=stocktake_id,
    ).select_related('material', 'location', 'stocktake'):
        if line.actual_qty is None:
            continue
        variance = line.actual_qty - line.system_qty
        if variance == 0:
            continue
        rows.append({
            'Mã kỳ': line.stocktake.number,
            'Mã NPL': line.material.code,
            'Tên NPL': line.material.name,
            'Vị trí': line.location.code,
            'Tồn HT': float(line.system_qty),
            'Tồn TT': float(line.actual_qty),
            'Chênh': float(variance),
        })
    return rows
