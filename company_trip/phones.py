"""SĐT trên form đăng ký du lịch hiển thị 0xxxxxxxxx."""

from hrm.phone import format_phone_vn, is_valid_vn_mobile, normalize_phone


def domestic_phone(value) -> str:
    """84912... → 0912.... Giữ nguyên nếu không phải SĐT di động Việt Nam."""
    raw = (value or '').strip()
    if not raw:
        return ''
    normalized = normalize_phone(raw)
    if is_valid_vn_mobile(normalized):
        return format_phone_vn(normalized)
    shown = format_phone_vn(raw)
    return shown or raw
