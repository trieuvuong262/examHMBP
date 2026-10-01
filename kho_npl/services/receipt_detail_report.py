"""Báo cáo chi tiết nhập — gom dòng phiếu nhập theo nhóm hàng, lọc theo ngày tạo phiếu."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from kho_npl.catalog_labels import unit_label
from kho_npl.choices import DOC_STATUS_CANCELLED, DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.material_search import apply_material_search
from kho_npl.models import Material, StockReceiptLine
from kho_npl.services.variant_groups import _group_display_name, _safe_group_dom_key, material_group_key

RECEIPT_DETAIL_STATUS_CHOICES = [
    (DOC_STATUS_POSTED, 'Đã nhập kho'),
    (DOC_STATUS_DRAFT, 'Đã tạo (nháp)'),
    ('all', 'Tất cả (trừ đã hủy)'),
]

RECEIPT_DETAIL_EXPORT_COLUMNS = [
    ('group_name', 'Nhóm hàng'),
    ('created_at', 'Ngày tạo phiếu'),
    ('receipt_date', 'Ngày nhập'),
    ('number', 'Số phiếu'),
    ('status', 'Trạng thái'),
    ('supplier', 'Nhà cung cấp'),
    ('po_number', 'Số PO'),
    ('code', 'Mã NPL'),
    ('name', 'Tên NPL'),
    ('qty', 'SL nhập'),
    ('unit', 'ĐVT nhập'),
    ('qty_base', 'SL theo ĐVT lẻ'),
    ('base_unit', 'ĐVT lẻ'),
    ('unit_price', 'Đơn giá / ĐVT nhập'),
    ('amount', 'Thành tiền'),
    ('location', 'Kho'),
    ('received_by', 'Người nhập'),
    ('notes', 'Ghi chú'),
]


def normalize_receipt_detail_status(raw: str | None) -> str:
    value = (raw or '').strip()
    valid = {key for key, _ in RECEIPT_DETAIL_STATUS_CHOICES}
    return value if value in valid else DOC_STATUS_POSTED


def _created_range(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), tz)
    return start, end


def _lines_qs(date_from: date, date_to: date, *, status: str, search: str, supplier: str):
    from kho_npl.stock_domain import domain_from_current_request

    start, end = _created_range(date_from, date_to)
    qs = (
        StockReceiptLine.objects.filter(
            receipt__stock_domain=domain_from_current_request(),
            receipt__created_at__gte=start,
            receipt__created_at__lt=end,
        )
        .exclude(receipt__status=DOC_STATUS_CANCELLED)
        .select_related(
            'receipt', 'receipt__supplier', 'receipt__received_by', 'receipt__received_by__profile',
            'material', 'material__unit', 'material__category',
            'line_unit', 'location',
        )
    )
    if status != 'all':
        qs = qs.filter(receipt__status=status)
    if supplier:
        qs = qs.filter(
            Q(receipt__supplier__name__icontains=supplier)
            | Q(receipt__supplier__code__icontains=supplier)
        )
    if search:
        material_ids = apply_material_search(Material.objects.all(), search).values('pk')
        qs = qs.filter(material_id__in=material_ids)
    return qs.order_by('receipt__created_at', 'receipt_id', 'pk')


def _user_name(user) -> str:
    if not user:
        return ''
    profile = getattr(user, 'profile', None)
    if profile and getattr(profile, 'full_name', ''):
        return profile.full_name
    return user.get_full_name() or user.username


def _line_row(line: StockReceiptLine) -> dict:
    receipt = line.receipt
    material = line.material
    qty_base = line.qty_base if line.qty_base else (line.received_qty or Decimal('0'))
    return {
        'line': line,
        'receipt': receipt,
        'material': material,
        'created_at': timezone.localtime(receipt.created_at) if receipt.created_at else None,
        'receipt_date': receipt.receipt_date,
        'number': receipt.number,
        'status': receipt.get_status_display(),
        'supplier': receipt.supplier.name if receipt.supplier_id else '',
        'po_number': receipt.po_number or '',
        'code': material.code,
        'name': material.name,
        'qty': line.received_qty or Decimal('0'),
        'unit': unit_label(line.line_unit or material.unit),
        'qty_base': qty_base,
        'base_unit': unit_label(material.unit),
        'unit_price': line.unit_price or Decimal('0'),
        'amount': line.amount,
        'location': line.location.name if line.location_id else '',
        'received_by': _user_name(receipt.received_by),
        'notes': line.notes or '',
    }


def report_receipt_detail(
    date_from: date,
    date_to: date,
    *,
    status: str = DOC_STATUS_POSTED,
    search: str = '',
    supplier: str = '',
) -> dict:
    status = normalize_receipt_detail_status(status)
    search = (search or '').strip()
    supplier = (supplier or '').strip()

    buckets: OrderedDict[tuple, list[dict]] = OrderedDict()
    for line in _lines_qs(date_from, date_to, status=status, search=search, supplier=supplier):
        buckets.setdefault(material_group_key(line.material), []).append(_line_row(line))

    groups = []
    total_amount = Decimal('0')
    total_lines = 0
    receipt_ids: set[int] = set()
    for key, rows in buckets.items():
        materials = list({r['material'].pk: r['material'] for r in rows}.values())
        rep = materials[0]
        qty_base = sum((r['qty_base'] for r in rows), Decimal('0'))
        amount = sum((r['amount'] for r in rows), Decimal('0'))
        group_receipt_ids = {r['receipt'].pk for r in rows}
        groups.append({
            'key': _safe_group_dom_key(key, rep),
            'group_name': _group_display_name(materials),
            'category': rep.category.name if rep.category_id else '',
            'base_unit': unit_label(rep.unit),
            'material_count': len(materials),
            'receipt_count': len(group_receipt_ids),
            'line_count': len(rows),
            'qty_base': qty_base,
            'amount': amount,
            'rows': rows,
        })
        total_amount += amount
        total_lines += len(rows)
        receipt_ids |= group_receipt_ids

    groups.sort(key=lambda g: (-g['amount'], (g['group_name'] or '').lower()))
    return {
        'groups': groups,
        'totals': {
            'group_count': len(groups),
            'receipt_count': len(receipt_ids),
            'line_count': total_lines,
            'amount': total_amount,
        },
    }


def report_receipt_detail_export_rows(date_from: date, date_to: date, **kwargs) -> list[dict]:
    data = report_receipt_detail(date_from, date_to, **kwargs)
    out = []
    for group in data['groups']:
        for row in group['rows']:
            item = {label: row.get(key, '') for key, label in RECEIPT_DETAIL_EXPORT_COLUMNS}
            item['Nhóm hàng'] = group['group_name']
            if row['created_at']:
                item['Ngày tạo phiếu'] = row['created_at'].strftime('%d/%m/%Y %H:%M')
            if row['receipt_date']:
                item['Ngày nhập'] = row['receipt_date'].strftime('%d/%m/%Y')
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
