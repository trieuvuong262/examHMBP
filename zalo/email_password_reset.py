"""Quên mật khẩu qua email — link đặt lại (Django PasswordResetTokenGenerator)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from audit.email_smtp import email_is_configured, send_portal_mail
from audit.services.password_sync import notify_external_password_changed
from hrm.models import Profile
from zalo.password_reset import PasswordResetError, resolve_user_for_password_reset

logger = logging.getLogger(__name__)

SESSION_EMAIL_USER_ID = 'jp_password_reset_email_user_id'

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@dataclass(frozen=True)
class EmailResetStartResult:
    ok: bool
    message: str
    needs_email: bool = False
    email_masked: str = ''


# email_is_configured re-exported from audit.email_smtp


def mask_email(email: str) -> str:
    text = (email or '').strip()
    if '@' not in text:
        return text or '—'
    local, _, domain = text.partition('@')
    if len(local) <= 1:
        masked_local = '*'
    elif len(local) == 2:
        masked_local = local[0] + '*'
    else:
        masked_local = local[0] + '***' + local[-1]
    return f'{masked_local}@{domain}'


def _user_can_reset(user: User | None) -> bool:
    if not user or not user.is_active:
        return False
    profile = getattr(user, 'profile', None)
    if profile is None:
        try:
            profile = Profile.objects.get(user=user)
        except Profile.DoesNotExist:
            return True  # admin / không có profile vẫn cho reset email
    if profile and not profile.is_employed and user.username != 'admin':
        return False
    return True


def build_reset_url(request, user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse('jp_password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
    return request.build_absolute_uri(path)


def send_password_reset_email(request, user: User) -> None:
    to_email = (user.email or '').strip()
    if not to_email:
        raise PasswordResetError('Tài khoản chưa có email.')
    if not email_is_configured():
        raise PasswordResetError(
            'Hệ thống email chưa cấu hình. Vui lòng liên hệ IT/HR để đặt lại mật khẩu.'
        )

    reset_url = build_reset_url(request, user)
    display = getattr(getattr(user, 'profile', None), 'full_name', '') or user.get_full_name() or user.username
    subject = 'JustPlay Portal — Đặt lại mật khẩu'
    ctx = {'display_name': display, 'reset_url': reset_url}
    body = (
        f'Xin chào {display},\n\n'
        f'Bạn (hoặc ai đó) đã yêu cầu đặt lại mật khẩu JustPlay Portal.\n\n'
        f'Mở liên kết sau để đặt mật khẩu mới (có thời hạn):\n'
        f'{reset_url}\n\n'
        f'Nếu bạn không yêu cầu, hãy bỏ qua email này — tài khoản vẫn an toàn.\n\n'
        f'— JustPlay Portal\n'
    )
    html_body = render_to_string('registration/password_reset_email.html', ctx)
    try:
        send_portal_mail(subject, body, [to_email], html_message=html_body)
    except Exception as exc:
        logger.exception('Gửi email reset mật khẩu thất bại user=%s', user.pk)
        raise PasswordResetError(
            'Không gửi được email. Thử lại sau hoặc liên hệ IT/HR.'
        ) from exc


def start_email_password_reset(identifier: str, request) -> EmailResetStartResult:
    user = resolve_user_for_password_reset(identifier)
    if not _user_can_reset(user):
        return EmailResetStartResult(
            ok=False,
            message='Không tìm thấy tài khoản hợp lệ. Kiểm tra tên đăng nhập / mã NS hoặc liên hệ HR.',
        )

    email = (user.email or '').strip()
    if not email:
        return EmailResetStartResult(
            ok=True,
            needs_email=True,
            message='Tài khoản chưa có email. Vui lòng nhập địa chỉ email để nhận link đặt lại mật khẩu.',
        )

    try:
        send_password_reset_email(request, user)
    except PasswordResetError as exc:
        return EmailResetStartResult(ok=False, message=str(exc))

    return EmailResetStartResult(
        ok=True,
        needs_email=False,
        email_masked=mask_email(email),
        message=(
            f'Đã gửi hướng dẫn đặt lại mật khẩu tới {mask_email(email)}. '
            f'Vui lòng kiểm tra hộp thư (kể cả thư mục spam).'
        ),
    )


def normalize_and_validate_email(raw: str) -> str:
    email = (raw or '').strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise PasswordResetError('Địa chỉ email không hợp lệ.')
    try:
        validate_email(email)
    except ValidationError as exc:
        raise PasswordResetError('Địa chỉ email không hợp lệ.') from exc
    return email


def save_user_email_and_send_reset(request, user_id: int, raw_email: str) -> EmailResetStartResult:
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise PasswordResetError('Phiên không hợp lệ. Vui lòng bắt đầu lại.') from exc

    if not _user_can_reset(user):
        raise PasswordResetError('Tài khoản không hợp lệ. Vui lòng bắt đầu lại.')

    email = normalize_and_validate_email(raw_email)
    clash = User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists()
    if clash:
        raise PasswordResetError('Email này đã được dùng bởi tài khoản khác. Chọn email khác hoặc liên hệ HR.')

    user.email = email
    user.save(update_fields=['email'])
    send_password_reset_email(request, user)
    return EmailResetStartResult(
        ok=True,
        needs_email=False,
        email_masked=mask_email(email),
        message=(
            f'Đã lưu email và gửi hướng dẫn đặt lại mật khẩu tới {mask_email(email)}. '
            f'Vui lòng kiểm tra hộp thư.'
        ),
    )


def get_user_from_uidb64(uidb64: str) -> User | None:
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


def set_password_from_email_token(
    uidb64: str,
    token: str,
    password1: str,
    password2: str,
) -> User:
    user = get_user_from_uidb64(uidb64)
    if not user or not default_token_generator.check_token(user, token):
        raise PasswordResetError('Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.')

    p1 = password1 or ''
    p2 = password2 or ''
    if p1 != p2:
        raise PasswordResetError('Mật khẩu nhập lại không khớp.')
    try:
        validate_password(p1, user=user)
    except ValidationError as exc:
        raise PasswordResetError(' '.join(exc.messages)) from exc

    with transaction.atomic():
        user.set_password(p1)
        user.save(update_fields=['password'])
        notify_external_password_changed(user, p1)
        profile = getattr(user, 'profile', None)
        if profile and profile.must_change_password:
            profile.must_change_password = False
            profile.save(update_fields=['must_change_password'])
    return user
