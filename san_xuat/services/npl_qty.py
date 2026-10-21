"""Công thức số lượng mua NPL — tách khỏi database để kiểm thử được."""

from __future__ import annotations

from decimal import Decimal


def _q(value) -> Decimal:
    try:
        return Decimal(str(value or '0'))
    except Exception:
        return Decimal('0')


def buy_qty(*, required, available, inbound) -> Decimal:
    """Thiếu cần mua = nhu cầu − tồn khả dụng − đã đặt chưa nhận (PR/PO còn hiệu lực)."""
    return max(Decimal('0'), _q(required) - _q(available) - _q(inbound))


def qty_still_due(*, ordered, qc_pass=0, qc_fail=0, closed=0, received=0) -> Decimal:
    """Còn phải giao. Hàng không đạt QC không tính là đã xong.

    Phiếu cũ chưa ghi QC thì số đã nhập được xem là đã đáp ứng.
    """
    passed = _q(qc_pass)
    failed = _q(qc_fail)
    done_close = _q(closed)
    if passed <= 0 and failed <= 0 and done_close <= 0:
        accepted = _q(received)
    else:
        accepted = passed
    return max(Decimal('0'), _q(ordered) - accepted - done_close)


def available_stock_increase(*, qc_pass) -> Decimal:
    """Chỉ số đạt QC, sau khi xác nhận nhập kho, mới cộng tồn khả dụng."""
    return max(Decimal('0'), _q(qc_pass))
