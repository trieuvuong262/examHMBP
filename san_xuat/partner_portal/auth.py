"""Phiên đăng nhập đối tác GC — tách hoàn toàn khỏi django.contrib.auth.

Session lưu id tài khoản + dấu băm mật khẩu: đổi/reset mật khẩu → mọi phiên cũ mất hiệu lực.
"""

from __future__ import annotations

from datetime import timedelta
from functools import wraps

from django.shortcuts import redirect
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from san_xuat.partner_models import GcPartnerAccount

SESSION_KEY = '_gc_account_id'
HASH_KEY = '_gc_account_hash'
MAX_FAILED = 5
LOCK_MINUTES = 15


class PartnerLoginError(Exception):
    pass


def _session_hash(account: GcPartnerAccount) -> str:
    return salted_hmac('gc-partner-session', account.password).hexdigest()


def get_session_account(request) -> GcPartnerAccount | None:
    session = getattr(request, 'session', None)
    if session is None:
        return None
    acc_id = session.get(SESSION_KEY)
    if not acc_id:
        return None
    acc = (
        GcPartnerAccount.objects.select_related('partner')
        .filter(pk=acc_id, is_active=True, partner__is_active=True)
        .first()
    )
    if acc is None or not constant_time_compare(session.get(HASH_KEY, ''), _session_hash(acc)):
        session.flush()
        return None
    return acc


def authenticate(username: str, password: str) -> GcPartnerAccount:
    """Kiểm tra đăng nhập + khoá tạm sau MAX_FAILED lần sai."""
    username = (username or '').strip().lower()
    acc = GcPartnerAccount.objects.select_related('partner').filter(username=username).first()
    generic = 'Sai tên đăng nhập hoặc mật khẩu.'
    if acc is None:
        GcPartnerAccount(password='').check_password(password or 'x')  # cân thời gian
        raise PartnerLoginError(generic)
    if acc.is_locked:
        raise PartnerLoginError('Tài khoản tạm khoá do nhập sai nhiều lần. Thử lại sau ít phút.')
    if not acc.check_password(password):
        acc.failed_logins += 1
        fields = ['failed_logins']
        if acc.failed_logins >= MAX_FAILED:
            acc.locked_until = timezone.now() + timedelta(minutes=LOCK_MINUTES)
            acc.failed_logins = 0
            fields.append('locked_until')
        acc.save(update_fields=fields)
        raise PartnerLoginError(generic)
    if not acc.is_active or not acc.partner.is_active:
        raise PartnerLoginError('Tài khoản đã bị khoá. Liên hệ JustPlay.')
    return acc


def login(request, account: GcPartnerAccount) -> None:
    request.session.cycle_key()
    request.session[SESSION_KEY] = account.pk
    request.session[HASH_KEY] = _session_hash(account)
    account.failed_logins = 0
    account.locked_until = None
    account.last_login = timezone.now()
    account.save(update_fields=['failed_logins', 'locked_until', 'last_login'])
    request.gc_account = account


def refresh_session_hash(request, account: GcPartnerAccount) -> None:
    request.session[HASH_KEY] = _session_hash(account)


def logout(request) -> None:
    request.session.flush()
    request.gc_account = None


def partner_login_required(view):
    """Bắt đăng nhập; tài khoản phải đổi MK thì chỉ vào được trang đổi MK."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        acc = getattr(request, 'gc_account', None)
        if acc is None:
            return redirect(f"/dang-nhap/?next={request.get_full_path()}")
        if acc.must_change_password and request.resolver_match.url_name != 'change_password':
            return redirect('change_password')
        return view(request, *args, **kwargs)

    return wrapper


def owner_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        acc = getattr(request, 'gc_account', None)
        if acc is None or acc.role != GcPartnerAccount.ROLE_OWNER:
            return redirect('home')
        return view(request, *args, **kwargs)

    return partner_login_required(wrapper)
