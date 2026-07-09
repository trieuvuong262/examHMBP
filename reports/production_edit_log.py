"""Mô tả chi tiết thay đổi công đoạn SX cho lịch sử chỉnh sửa."""

from __future__ import annotations

from decimal import Decimal

from reports.models import DailyWorkReport, ProductionShiftProduct
from reports.production_hourly import (
    _build_proxy_time_snapshot,
    _proxy_session_has_input,
    format_production_quantity,
    parse_decimal,
    parse_int,
    parse_non_negative_decimal,
    session_time_displays,
)


def snapshot_production_session(product: ProductionShiftProduct) -> dict[str, str]:
    """Ảnh chụp trạng thái một công đoạn để so sánh trước / sau."""
    start, end = session_time_displays(product)
    norm = product.norm_per_hour
    return {
        'code': (product.product_code or '').strip() or '—',
        'process': (product.process_name or '').strip() or '—',
        'norm': format_production_quantity(norm) if norm and norm > 0 else '—',
        'quantity': format_production_quantity(product.total_quantity or 0),
        'damaged': str(int(product.total_damaged_quantity or 0)),
        'time': f'{start}–{end}' if start and end else '—',
        'note': (product.completion_note or '').strip() or '—',
    }


def snapshot_proxy_session_form(
    sess: dict,
    *,
    snapshot: dict[int, dict] | None = None,
    content_edit_only: bool = False,
) -> dict[str, str]:
    """Ảnh chụp công đoạn từ dữ liệu form nhập hộ."""
    product_id = parse_int(sess.get('product_id'), -1)
    start = (sess.get('start_time') or '').strip()
    end = (sess.get('end_time') or '').strip()
    if content_edit_only and snapshot and product_id >= 0 and product_id in snapshot:
        start = snapshot[product_id].get('start_time') or start
        end = snapshot[product_id].get('end_time') or end

    norm = parse_decimal(sess.get('norm'))
    total = parse_non_negative_decimal(sess.get('total'), default=Decimal('0'))
    damaged = parse_int(sess.get('damaged'))
    return {
        'code': (sess.get('code') or '').strip() or '—',
        'process': (sess.get('process') or '').strip() or '—',
        'norm': format_production_quantity(norm) if norm and norm > 0 else '—',
        'quantity': format_production_quantity(total),
        'damaged': str(max(0, damaged)),
        'time': f'{start}–{end}' if start and end else '—',
        'note': (sess.get('note') or '').strip() or '—',
    }


def format_snapshot_line(snap: dict[str, str]) -> str:
    parts = [
        f"Mã {snap['code']}",
        f"CD {snap['process']}",
        f"SL {snap['quantity']}",
        f"ĐM {snap['norm']}/giờ",
        f"Giờ {snap['time']}",
    ]
    if snap.get('damaged', '0') != '0':
        parts.append(f"Hỏng {snap['damaged']}")
    if snap.get('note', '—') != '—':
        parts.append(f"GC: {snap['note']}")
    return ', '.join(parts)


def format_session_change_detail(
    *,
    before: dict[str, str] | None = None,
    after: dict[str, str] | None = None,
) -> str:
    lines: list[str] = []
    if before:
        lines.append(f"Trước: {format_snapshot_line(before)}")
    if after:
        lines.append(f"Sau: {format_snapshot_line(after)}")
    return '\n'.join(lines)


def collect_proxy_save_change_detail(
    report: DailyWorkReport,
    sessions: list[dict],
    *,
    content_edit_only: bool,
) -> str:
    """So sánh công đoạn trước và sau khi lưu nhập hộ."""
    time_snapshot = _build_proxy_time_snapshot(report) if content_edit_only and report.pk else {}
    old_by_id = {
        product.id: snapshot_production_session(product)
        for product in report.production_products.all()
    }

    referenced_ids: set[int] = set()
    lines: list[str] = []

    for sess in sessions:
        if not _proxy_session_has_input(sess):
            continue
        product_id = parse_int(sess.get('product_id'), -1)
        new_snap = snapshot_proxy_session_form(
            sess,
            snapshot=time_snapshot,
            content_edit_only=content_edit_only,
        )
        if product_id >= 0 and product_id in old_by_id:
            referenced_ids.add(product_id)
            old_snap = old_by_id[product_id]
            if old_snap != new_snap:
                label = new_snap['code'] if new_snap['code'] != '—' else old_snap['code']
                detail = format_session_change_detail(before=old_snap, after=new_snap)
                lines.append(f"• {label}:\n{detail}")
        else:
            label = new_snap['code']
            lines.append(f"• Thêm {label}:\nSau: {format_snapshot_line(new_snap)}")

    for product_id in sorted(set(old_by_id) - referenced_ids):
        old_snap = old_by_id[product_id]
        label = old_snap['code']
        lines.append(f"• Xóa {label}:\nTrước: {format_snapshot_line(old_snap)}")

    return '\n\n'.join(lines)


def collect_new_sessions_detail(report: DailyWorkReport) -> str:
    """Liệt kê công đoạn mới sau khi nhập hộ / nộp báo cáo."""
    lines: list[str] = []
    for product in report.production_products.order_by('sort_order', 'id'):
        snap = snapshot_production_session(product)
        lines.append(f"• {snap['code']}:\nSau: {format_snapshot_line(snap)}")
    return '\n\n'.join(lines)


def collect_productivity_update_detail(
    report: DailyWorkReport,
    delete_ids: list[int],
    norms: dict[int, object],
    codes: dict[int, str],
    processes: dict[int, str],
) -> str:
    """Chi tiết chỉnh sửa trên tab báo cáo năng suất (mã, CD, định mức, xóa)."""
    products = {product.id: product for product in report.production_products.all()}
    lines: list[str] = []

    for product_id in delete_ids:
        product = products.get(product_id)
        if not product:
            continue
        snap = snapshot_production_session(product)
        lines.append(f"• Xóa {snap['code']}:\nTrước: {format_snapshot_line(snap)}")

    skip_ids = set(delete_ids)
    product_ids = (set(norms) | set(codes) | set(processes)) - skip_ids
    for product_id in sorted(product_ids):
        product = products.get(product_id)
        if not product:
            continue
        before = snapshot_production_session(product)
        after = dict(before)
        if product_id in codes:
            after['code'] = str(codes[product_id] or '').strip() or '—'
        if product_id in processes:
            after['process'] = str(processes[product_id] or '').strip() or '—'
        if product_id in norms:
            norm = norms[product_id]
            after['norm'] = (
                format_production_quantity(norm) if norm and norm > 0 else '—'
            )
        if before == after:
            continue
        label = after['code'] if after['code'] != '—' else before['code']
        detail = format_session_change_detail(before=before, after=after)
        lines.append(f"• {label}:\n{detail}")

    return '\n\n'.join(lines)
