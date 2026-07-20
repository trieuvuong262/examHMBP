"""API gửi OTP qua Zalo OA (ZBS) — dùng từ flow quên mật khẩu (P2)."""

from __future__ import annotations

from hrm.phone import is_valid_vn_mobile, normalize_phone
from zalo.client import ZaloAPIError, ZaloClient, zalo_is_ready


def send_password_reset_otp(phone: str, otp: str, *, tracking_id: str | None = None) -> dict:
    """
    Gửi OTP quên mật khẩu tới SĐT (nhận dạng tự do → chuẩn hóa 84…).
    Raises ``ZaloAPIError`` nếu cấu hình thiếu / API lỗi.
    """
    if not zalo_is_ready():
        raise ZaloAPIError(
            'Zalo OTP chưa sẵn sàng. Kiểm tra ZALO_* trong .env và '
            '`python manage.py zalo_status`.'
        )
    normalized = normalize_phone(phone)
    if not is_valid_vn_mobile(normalized):
        raise ZaloAPIError('SĐT không hợp lệ để gửi OTP Zalo.')
    return ZaloClient().send_otp(phone=normalized, otp=otp, tracking_id=tracking_id)
