"""Chuẩn hóa SĐT Việt Nam cho hồ sơ NS / Zalo OTP."""

from __future__ import annotations

import re

# Mobile VN lưu dạng E.164 không dấu +: 84 + 9 số (03/05/07/08/09…)
VN_MOBILE_RE = re.compile(r'^84[35789]\d{8}$')
_NON_DIGIT_RE = re.compile(r'[^\d+]')


def normalize_phone(value) -> str:
    """
    Chuẩn hóa SĐT → ``84xxxxxxxxx`` (không ``+``).
    Trả ``''`` nếu trống. Không raise — dùng ``is_valid_vn_mobile`` để kiểm.
    """
    if value is None:
        return ''
    # Excel đôi khi đọc SĐT thành float (912345678.0)
    if isinstance(value, float):
        if value != value:  # NaN
            return ''
        value = str(int(value)) if value == int(value) else str(value)
    elif isinstance(value, int):
        value = str(value)

    raw = str(value).strip()
    if not raw or raw.lower() in {'nan', 'none'}:
        return ''

    digits = _NON_DIGIT_RE.sub('', raw)
    if digits.startswith('+'):
        digits = digits[1:]
    if digits.startswith('00'):
        digits = digits[2:]

    if digits.startswith('0') and len(digits) == 10:
        digits = '84' + digits[1:]
    elif len(digits) == 9 and digits[0] in '35789':
        digits = '84' + digits

    return digits


def is_valid_vn_mobile(phone: str) -> bool:
    return bool(phone) and bool(VN_MOBILE_RE.fullmatch(phone))


def format_phone_vn(phone: str) -> str:
    """Hiển thị ``0xxxxxxxxx`` từ bản lưu ``84xxxxxxxxx``."""
    if not phone:
        return ''
    if phone.startswith('84') and len(phone) == 11:
        return '0' + phone[2:]
    return phone


def mask_phone_vn(phone: str) -> str:
    """Mask cho OTP / UI công khai: ``09****5678``."""
    display = format_phone_vn(phone)
    if len(display) < 7:
        return display or '—'
    return f'{display[:2]}****{display[-4:]}'
