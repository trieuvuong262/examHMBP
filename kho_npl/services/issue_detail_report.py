"""Báo cáo chi tiết xuất — gom dòng phiếu xuất theo nhóm hàng, lọc theo ngày tạo phiếu."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from kho_npl.catalog_labels import unit_label
from kho_npl.choices import DOC_STATUS_CANCELLED, DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.material_search import apply_material_search
from kho_npl.models import Material, StockIssueLine
from kho_npl.services.variant_groups import _group_display_name, _safe_group_dom_key, material_group_key

ISSUE_DETAIL_STATUS_CHOICES = [
    (DOC_STATUS_POSTED, 'Đã xuất kho'),
    (DOC_STATUS_DRAFT, 'Đã tạo (nháp)'),
    ('all', 'Tất cả (trừ đã hủy)'),
]

ISSUE_DETAIL_EXPORT_COLUMNS = [
    ('group_name', 'Nhóm hàng'),
    ('created_at', 'Ngày tạo phiếu'),
    ('issue_date', 'Ngày xuất'),
    ('number', 'Số phiếu'),
    ('status', 'Trạng thái'),
    ('product_code', 'Sản phẩm (mẫu)'),
    ('code', 'Mã NPL'),
    ('name', 'Tên NPL'),
    ('qty', 'SL xuất'),
    ('unit', 'ĐVT xuất'),
    ('qty_base', 'SL theo ĐVT lẻ'),
    ('base_unit', 'ĐVT lẻ'),
    ('unit_price', 'Đơn giá / ĐVT xuất'),
    ('amount', 'Thành tiền'),
    ('recipient', 'Người nhận'),
    ('issue_type', 'Lý do xuất'),
    ('notes', 'Ghi chú'),
]


def normalize_issue_detail_status(raw: str | None) -> str:
    value = (raw or '').strip()
    valid = {key for key, _ in ISSUE_DETAIL_STATUS_CHOICES}
    return value if value in valid else DOC_STATUS_POSTED


def _created_range(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), tz)
    return start, end


def _lines_qs(date_from: date, date_to: date, *, status: str, search: str, product_code: str):
    from kho_npl.stock_domain import domain_from_current_request

    start, end = _created_range(date_from, date_to)
    qs = (
        StockIssueLine.objects.filter(
            issue__stock_domain=domain_from_current_request(),
            issue__created_at__gte=start,
            issue__created_at__lt=end,
        )
        .exclude(issue__status=DOC_STATUS_CANCELLED)
        .select_related(
            'issue', 'issue__recipient', 'issue__recipient__profile',
            'material', 'material__unit', 'material__category',
            'line_unit', 'location',
        )
    )
    if status != 'all':
        qs = qs.filter(issue__status=status)
    if product_code:
        qs = qs.filter(issue__product_code__icontains=product_code)
    if search:
        material_ids = apply_material_search(Material.objects.all(), search).values('pk')
        qs = qs.filter(material_id__in=material_ids)
    return qs.order_by('issue__created_at', 'issue_id', 'pk')


def _line_row(line: StockIssueLine) -> dict:
    issue = line.issue
    material = line.material
    qty_base = line.qty_base if line.qty_base else (line.quantity or Decimal('0'))
    return {
        'line': line,
        'issue': issue,
        'material': material,
        'created_at': timezone.localtime(issue.created_at) if issue.created_at else None,
        'issue_date': issue.issue_date,
        'number': issue.number,
        'status': issue.get_status_display(),
        'product_code': issue.product_code or '',
        'code': material.code,
        'name': material.name,
        'qty': line.quantity or Decimal('0'),
        'unit': unit_label(line.line_unit or material.unit),
        'qty_base': qty_base,
        'base_unit': unit_label(material.unit),
        'unit_price': line.selected_unit_price,
        'amount': line.amount,
        'recipient': issue.display_recipient_name or '',
        'issue_type': issue.issue_type or '',
        'notes': line.notes or '',
    }


def report_issue_detail(
    date_from: date,
    date_to: date,
    *,
    status: str = DOC_STATUS_POSTED,
    search: str = '',
    product_code: str = '',
) -> dict:
    status = normalize_issue_detail_status(status)
    search = (search or '').strip()
    product_code = (product_code or '').strip()

    buckets: OrderedDict[tuple, list[dict]] = OrderedDict()
    for line in _lines_qs(date_from, date_to, status=status, search=search, product_code=product_code):
        buckets.setdefault(material_group_key(line.material), []).append(_line_row(line))

    groups = []
    total_amount = Decimal('0')
    total_lines = 0
    issue_ids: set[int] = set()
    for key, rows in buckets.items():
        materials = list({r['material'].pk: r['material'] for r in rows}.values())
        rep = materials[0]
        qty_base = sum((r['qty_base'] for r in rows), Decimal('0'))
        amount = sum((r['amount'] for r in rows), Decimal('0'))
        group_issue_ids = {r['issue'].pk for r in rows}
        groups.append({
            'key': _safe_group_dom_key(key, rep),
            'group_name': _group_display_name(materials),
            'category': rep.category.name if rep.category_id else '',
            'base_unit': unit_label(rep.unit),
            'material_count': len(materials),
            'issue_count': len(group_issue_ids),
            'line_count': len(rows),
            'qty_base': qty_base,
            'amount': amount,
            'rows': rows,
        })
        total_amount += amount
        total_lines += len(rows)
        issue_ids |= group_issue_ids

    groups.sort(key=lambda g: (-g['amount'], (g['group_name'] or '').lower()))
    return {
        'groups': groups,
        'totals': {
            'group_count': len(groups),
            'issue_count': len(issue_ids),
            'line_count': total_lines,
            'amount': total_amount,
        },
    }


def report_issue_detail_export_rows(date_from: date, date_to: date, **kwargs) -> list[dict]:
    data = report_issue_detail(date_from, date_to, **kwargs)
    out = []
    for group in data['groups']:
        for row in group['rows']:
            item = {label: row.get(key, '') for key, label in ISSUE_DETAIL_EXPORT_COLUMNS}
            item['Nhóm hàng'] = group['group_name']
            if row['created_at']:
                item['Ngày tạo phiếu'] = row['created_at'].strftime('%d/%m/%Y %H:%M')
            if row['issue_date']:
                item['Ngày xuất'] = row['issue_date'].strftime('%d/%m/%Y')
            out.append(item)
        out.append({
            'Nhóm hàng': f'Cộng nhóm {group["group_name"]}',
            'SL theo ĐVT lẻ': group['qty_base'],
            'ĐVT lẻ': group['base_unit'],
            'Thành tiền': group['amount'],
        })
    if out:
        out.append({'Nhóm hàng': 'Tổng cộng', 'Thành tiền': data['totals']['amount']})
    return out
