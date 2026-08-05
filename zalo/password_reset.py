"""Flow quên mật khẩu: yêu cầu OTP → xác thực → đặt MK mới."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.login_security import resolve_user_by_login_identifier
from audit.services.password_sync import notify_external_password_changed
from hrm.models import Profile
from hrm.phone import format_phone_vn, is_valid_vn_mobile, mask_phone_vn, normalize_phone
from zalo.client import ZaloAPIError
from zalo.models import PasswordResetOtp
from zalo.services import send_password_reset_otp

logger = logging.getLogger(__name__)

SESSION_KEY = 'jp_password_reset_token'


class PasswordResetError(Exception):
    """Lỗi nghiệp vụ hiển thị được cho user (không leak chi tiết nội bộ)."""


@dataclass(frozen=True)
class RequestOtpResult:
    ok: bool
    message: str
    phone_masked: str = ''
    cooldown_seconds: int = 0
    session_token: str = ''


def _otp_ttl() -> int:
    return max(60, int(getattr(settings, 'ZALO_OTP_TTL_SECONDS', 300) or 300))


def _otp_length() -> int:
    return max(4, min(8, int(getattr(settings, 'ZALO_OTP_LENGTH', 6) or 6)))


def _cooldown() -> int:
    return max(30, int(getattr(settings, 'ZALO_OTP_COOLDOWN_SECONDS', 60) or 60))


def _max_per_hour() -> int:
    return max(1, int(getattr(settings, 'ZALO_OTP_MAX_PER_HOUR', 5) or 5))


def _hash_otp(code: str) -> str:
    raw = f'{settings.SECRET_KEY}:password-reset-otp:{code}'.encode()
    return hashlib.sha256(raw).hexdigest()


def _generate_otp() -> str:
    length = _otp_length()
    # Tránh leading zero mất khi parse — giữ dạng string đủ độ dài
    upper = 10 ** length
    return f'{secrets.randbelow(upper):0{length}d}'


def resolve_user_for_password_reset(identifier: str) -> User | None:
    """Username hoặc mã NS."""
    text = (identifier or '').strip()
    if not text:
        return None
    user = resolve_user_by_login_identifier(text)
    if user:
        return user
    profile = (
        Profile.objects.filter(employee_code__iexact=text)
        .select_related('user')
        .first()
    )
    return profile.user if profile else None


def _user_eligible(user: User | None) -> tuple[bool, str]:
    """Trả (ok, phone_normalized). phone rỗng nếu không đủ điều kiện."""
    if not user or not user.is_active:
        return False, ''
    profile = getattr(user, 'profile', None)
    if profile is None:
        try:
            profile = Profile.objects.get(user=user)
        except Profile.DoesNotExist:
            return False, ''
    if not profile.is_employed:
        return False, ''
    phone = normalize_phone(profile.phone or '')
    if not is_valid_vn_mobile(phone):
        return False, ''
    return True, phone


def _rate_limited(user: User, ip: str | None) -> bool:
    since = timezone.now() - timezone.timedelta(hours=1)
    qs = PasswordResetOtp.objects.filter(created_at__gte=since)
    user_count = qs.filter(user=user).count()
    if user_count >= _max_per_hour():
        return True
    if ip:
        ip_count = qs.filter(ip_address=ip).count()
        if ip_count >= _max_per_hour() * 3:
            return True
    return False


def _latest_pending(user: User) -> PasswordResetOtp | None:
    return (
        PasswordResetOtp.objects.filter(user=user, status=PasswordResetOtp.STATUS_PENDING)
        .order_by('-created_at')
        .first()
    )


def request_password_reset_otp(
    identifier: str,
    *,
    ip: str | None = None,
) -> RequestOtpResult:
    """
    Luôn trả thông điệp trung tính nếu identifier không hợp lệ
    (tránh lộ tài khoản tồn tại / có SĐT).
    """
    generic_ok = (
        'Nếu tài khoản hợp lệ và đã có số điện thoại, mã OTP đã được gửi tới Zalo.'
    )
    generic_fail_config = (
        'Tính năng quên mật khẩu qua Zalo chưa sẵn sàng. Vui lòng liên hệ IT/HR.'
    )

    from zalo.client import zalo_is_ready

    if not zalo_is_ready():
        return RequestOtpResult(ok=False, message=generic_fail_config)

    user = resolve_user_for_password_reset(identifier)
    eligible, phone = _user_eligible(user)
    if not eligible or not user:
        # Delay nhẹ không cần — generic message
        return RequestOtpResult(ok=True, message=generic_ok)

    if _rate_limited(user, ip):
        return RequestOtpResult(
            ok=False,
            message='Bạn đã yêu cầu quá nhiều lần. Thử lại sau khoảng 1 giờ hoặc liên hệ HR.',
        )

    latest = _latest_pending(user)
    if latest and not latest.is_expired():
        elapsed = (timezone.now() - latest.created_at).total_seconds()
        wait = _cooldown() - int(elapsed)
        if wait > 0:
            return RequestOtpResult(
                ok=False,
                message=f'Vui lòng đợi {wait} giây trước khi gửi lại OTP.',
                phone_masked=mask_phone_vn(phone),
                cooldown_seconds=wait,
            )

    otp = _generate_otp()
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timezone.timedelta(seconds=_otp_ttl())

    with transaction.atomic():
        PasswordResetOtp.objects.filter(
            user=user,
            status__in=(PasswordResetOtp.STATUS_PENDING, PasswordResetOtp.STATUS_VERIFIED),
        ).update(status=PasswordResetOtp.STATUS_USED, used_at=timezone.now())

        record = PasswordResetOtp.objects.create(
            user=user,
            code_hash=_hash_otp(otp),
            session_token=token,
            phone=phone,
            ip_address=ip or None,
            expires_at=expires_at,
        )

    try:
        send_password_reset_otp(
            phone,
            otp,
            tracking_id=f'jp-reset-{record.pk}',
        )
    except ZaloAPIError as exc:
        logger.warning('Gửi OTP Zalo thất bại user=%s: %s', user.pk, exc)
        record.delete()
        return RequestOtpResult(
            ok=False,
            message='Không gửi được OTP qua Zalo. Thử lại sau hoặc liên hệ IT/HR.',
        )

    minutes = max(1, _otp_ttl() // 60)
    return RequestOtpResult(
        ok=True,
        message=(
            f'Đã gửi mã OTP tới Zalo {mask_phone_vn(phone)}. '
            f'Mã hết hạn sau {minutes} phút.'
        ),
        phone_masked=mask_phone_vn(phone),
        session_token=token,
    )


def get_reset_record(session_token: str | None) -> PasswordResetOtp | None:
    token = (session_token or '').strip()
    if not token:
        return None
    return (
        PasswordResetOtp.objects.select_related('user', 'user__profile')
        .filter(session_token=token)
        .first()
    )


def verify_password_reset_otp(session_token: str | None, otp_code: str) -> PasswordResetOtp:
    record = get_reset_record(session_token)
    if not record or record.status not in (
        PasswordResetOtp.STATUS_PENDING,
        PasswordResetOtp.STATUS_VERIFIED,
    ):
        raise PasswordResetError('Phiên đặt lại mật khẩu không hợp lệ. Vui lòng bắt đầu lại.')

    if record.is_expired():
        raise PasswordResetError('Mã OTP đã hết hạn. Vui lòng yêu cầu mã mới.')

    if record.status == PasswordResetOtp.STATUS_VERIFIED:
        return record

    code = (otp_code or '').strip()
    if not code.isdigit():
        raise PasswordResetError('Mã OTP không hợp lệ.')

    if record.attempts_left() <= 0:
        raise PasswordResetError('Đã nhập sai quá số lần cho phép. Vui lòng yêu cầu mã mới.')

    record.attempts = int(record.attempts or 0) + 1
    if not secrets.compare_digest(record.code_hash, _hash_otp(code)):
        record.save(update_fields=['attempts'])
        left = record.attempts_left()
        if left <= 0:
            raise PasswordResetError('Đã nhập sai quá số lần cho phép. Vui lòng yêu cầu mã mới.')
        raise PasswordResetError(f'Mã OTP không đúng. Còn {left} lần thử.')

    record.status = PasswordResetOtp.STATUS_VERIFIED
    record.verified_at = timezone.now()
    record.save(update_fields=['attempts', 'status', 'verified_at'])
    return record


def complete_password_reset(
    session_token: str | None,
    new_password1: str,
    new_password2: str,
) -> User:
    record = get_reset_record(session_token)
    if not record or record.status != PasswordResetOtp.STATUS_VERIFIED:
        raise PasswordResetError('Chưa xác thực OTP hoặc phiên đã hết hạn. Vui lòng bắt đầu lại.')
    if record.is_expired():
        raise PasswordResetError('Phiên đặt lại mật khẩu đã hết hạn. Vui lòng bắt đầu lại.')

    p1 = new_password1 or ''
    p2 = new_password2 or ''
    if p1 != p2:
        raise PasswordResetError('Mật khẩu nhập lại không khớp.')
    try:
        validate_password(p1, user=record.user)
    except ValidationError as exc:
        raise PasswordResetError(' '.join(exc.messages)) from exc

    user = record.user
    with transaction.atomic():
        user.set_password(p1)
        user.save(update_fields=['password'])
        notify_external_password_changed(user, p1)
        profile = getattr(user, 'profile', None)
        if profile and profile.must_change_password:
            profile.must_change_password = False
            profile.save(update_fields=['must_change_password'])
        record.status = PasswordResetOtp.STATUS_USED
        record.used_at = timezone.now()
        record.save(update_fields=['status', 'used_at'])

    return user


def phone_display_for_record(record: PasswordResetOtp | None) -> str:
    if not record:
        return ''
    return mask_phone_vn(record.phone) or format_phone_vn(record.phone)
