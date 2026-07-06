"""Giới hạn đăng nhập — khóa tài khoản; chặn IP blacklist / bot quét exploit."""

from __future__ import annotations

import ipaddress

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from audit.models import IpLoginBlock, LoginSecurityConfig, UserLoginLock

User = get_user_model()


def max_user_attempts() -> int:
    return int(getattr(settings, 'LOGIN_LOCK_MAX_ATTEMPTS', 10))


def max_ip_attempts() -> int:
    return int(getattr(settings, 'LOGIN_IP_BLOCK_MAX_ATTEMPTS', 10))


def it_contact_display() -> str:
    return getattr(settings, 'PORTAL_IT_CONTACT', 'IT — liên hệ qua nội bộ Just Play')


def get_security_config() -> LoginSecurityConfig:
    return LoginSecurityConfig.get_solo()


def parse_ip_list(text: str) -> tuple[list[str], list[str]]:
    """Tách danh sách IP từ textarea; trả (hợp lệ, token lỗi)."""
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for raw in (text or '').replace(',', '\n').splitlines():
        token = raw.strip()
        if not token:
            continue
        try:
            ip = str(ipaddress.ip_address(token))
        except ValueError:
            invalid.append(token)
            continue
        if ip in seen:
            continue
        seen.add(ip)
        valid.append(ip)
    return valid, invalid


def format_ip_list(ips: list[str] | None) -> str:
    return '\n'.join(ips or [])


def get_wan_whitelist() -> list[str]:
    return list(get_security_config().wan_whitelist_ips or [])


def get_ip_blacklist() -> list[str]:
    return list(get_security_config().ip_blacklist or [])


def is_ip_whitelisted(ip: str | None) -> bool:
    if not ip:
        return False
    return ip in get_wan_whitelist()


def is_ip_blacklisted(ip: str | None) -> bool:
    if not ip:
        return False
    return ip in get_ip_blacklist()


def save_login_security_config(
    *,
    wan_whitelist_text: str,
    ip_blacklist_text: str,
    admin_user,
) -> tuple[LoginSecurityConfig, list[str], list[str]]:
    """
    Lưu cấu hình IP. Trả (config, invalid_wan, invalid_blacklist).
    """
    wan_ips, invalid_wan = parse_ip_list(wan_whitelist_text)
    blacklist_ips, invalid_blacklist = parse_ip_list(ip_blacklist_text)
    overlap = set(wan_ips) & set(blacklist_ips)
    if overlap:
        invalid_blacklist.extend(sorted(overlap))

    config = get_security_config()
    if not invalid_wan and not invalid_blacklist:
        config.wan_whitelist_ips = wan_ips
        config.ip_blacklist = blacklist_ips
        config.updated_by = admin_user
        config.save(update_fields=['wan_whitelist_ips', 'ip_blacklist', 'updated_by', 'updated_at'])
    return config, invalid_wan, invalid_blacklist


def blacklist_suggestions(*, limit: int = 25) -> list[str]:
    """Gợi ý IP blacklist từ log chặn spam."""
    whitelist = set(get_wan_whitelist())
    blacklist = set(get_ip_blacklist())
    suggestions: list[str] = []
    seen: set[str] = set()

    def _add(ip: str | None) -> None:
        if not ip or ip in seen or ip in whitelist or ip in blacklist:
            return
        seen.add(ip)
        suggestions.append(ip)

    for row in IpLoginBlock.objects.filter(blocked_at__isnull=False, unlocked_at__isnull=True).order_by('-blocked_at')[:limit]:
        _add(row.ip_address)
    for row in IpLoginBlock.objects.filter(unknown_username_count__gt=0).order_by('-unknown_username_count', '-last_failed_at')[:limit]:
        _add(row.ip_address)
    for row in IpLoginBlock.objects.filter(failed_attempts__gte=max_ip_attempts()).order_by('-failed_attempts')[:limit]:
        _add(row.ip_address)
    return suggestions[:limit]


def resolve_user_by_login_identifier(identifier: str):
    """Tra cứu user theo username (không hỗ trợ đăng nhập bằng email)."""
    text = (identifier or '').strip()
    if not text:
        return None
    return User.objects.filter(username__iexact=text).order_by('id').first()


def get_user_lock(user) -> UserLoginLock | None:
    if not user:
        return None
    return UserLoginLock.objects.filter(user=user).first()


def is_user_locked(user) -> bool:
    lock = get_user_lock(user)
    return bool(lock and lock.is_locked)


def get_ip_block(ip: str | None) -> IpLoginBlock | None:
    if not ip:
        return None
    return IpLoginBlock.objects.filter(ip_address=ip).first()


def is_ip_blocked(ip: str | None) -> bool:
    if not ip:
        return False
    if is_ip_blacklisted(ip):
        return True
    if is_ip_whitelisted(ip):
        return False
    block = get_ip_block(ip)
    return bool(block and block.is_blocked)


def block_ip_for_form_spam(
    ip: str | None,
    *,
    sample_fields: list[str] | None = None,
    reason: str = 'form-spam',
) -> bool:
    """Chặn ngay IP bot quét / exploit (form rác, JSP, shell, ZAP…)."""
    if not ip or is_ip_whitelisted(ip):
        return False
    if is_ip_blacklisted(ip):
        return True

    row, _ = IpLoginBlock.objects.get_or_create(ip_address=ip)
    if row.is_blocked:
        return True

    now = timezone.now()
    row.blocked_at = now
    row.unlocked_at = None
    row.unlocked_by = None
    row.last_failed_at = now
    if sample_fields or reason:
        marker = reason or 'form-spam'
        if sample_fields:
            marker = f'{marker}:' + ','.join(str(x)[:40] for x in sample_fields[:8])
        row.sample_usernames = _append_username_sample(row.sample_usernames or [], marker)
    row.save(
        update_fields=[
            'blocked_at',
            'unlocked_at',
            'unlocked_by',
            'last_failed_at',
            'sample_usernames',
        ],
    )
    return True


def remaining_user_attempts(user) -> int:
    lock = get_user_lock(user)
    if not lock or lock.is_locked:
        return 0
    return max(0, max_user_attempts() - lock.failed_attempts)


def _append_username_sample(samples: list, username: str, *, limit: int = 12) -> list:
    name = (username or '').strip()
    if not name:
        return samples
    out = [name] + [s for s in samples if s.lower() != name.lower()]
    return out[:limit]


def record_failed_login(*, username: str, ip: str | None) -> dict:
    """
    Ghi nhận lần đăng nhập thất bại.
    Trả về flags: user_locked, ip_blocked, user_exists, remaining.
    """
    user = resolve_user_by_login_identifier(username)
    result = {
        'user': user,
        'user_locked': False,
        'ip_blocked': False,
        'user_exists': user is not None,
        'remaining': max_user_attempts(),
    }

    skip_ip_spam = is_ip_whitelisted(ip)

    if ip and not skip_ip_spam:
        ip_row, _ = IpLoginBlock.objects.get_or_create(ip_address=ip)
        if not ip_row.is_blocked:
            ip_row.failed_attempts += 1
            ip_row.last_failed_at = timezone.now()
            if not user:
                ip_row.unknown_username_count += 1
                ip_row.sample_usernames = _append_username_sample(
                    ip_row.sample_usernames or [],
                    username,
                )
            ip_row.save(
                update_fields=[
                    'failed_attempts',
                    'last_failed_at',
                    'unknown_username_count',
                    'sample_usernames',
                ],
            )

    if user and not is_user_locked(user):
        lock, _ = UserLoginLock.objects.get_or_create(
            user=user,
            defaults={'username_snapshot': user.username},
        )
        if lock.username_snapshot != user.username:
            lock.username_snapshot = user.username
        lock.failed_attempts += 1
        lock.last_failed_at = timezone.now()
        if ip:
            lock.last_ip = ip
        if lock.failed_attempts >= max_user_attempts():
            lock.locked_at = timezone.now()
            lock.unlocked_at = None
            lock.unlocked_by = None
            lock.save()
            result['user_locked'] = True
            result['remaining'] = 0
        else:
            lock.save()
            result['remaining'] = remaining_user_attempts(user)
    elif user:
        result['user_locked'] = True
        result['remaining'] = 0

    if ip and is_ip_blocked(ip):
        result['ip_blocked'] = True

    return result


def record_successful_login(user) -> None:
    """Đăng nhập thành công — xóa đếm lỗi (không tự mở khóa do admin)."""
    if not user:
        return
    lock = get_user_lock(user)
    if not lock:
        return
    if lock.is_locked:
        return
    if lock.failed_attempts:
        lock.failed_attempts = 0
        lock.save(update_fields=['failed_attempts'])


def unlock_user_account(*, lock: UserLoginLock, admin_user) -> None:
    lock.failed_attempts = 0
    lock.locked_at = None
    lock.unlocked_at = timezone.now()
    lock.unlocked_by = admin_user
    lock.save(
        update_fields=[
            'failed_attempts',
            'locked_at',
            'unlocked_at',
            'unlocked_by',
        ],
    )


def unlock_ip_block(*, block: IpLoginBlock, admin_user) -> None:
    block.failed_attempts = 0
    block.unknown_username_count = 0
    block.blocked_at = None
    block.unlocked_at = timezone.now()
    block.unlocked_by = admin_user
    block.save(
        update_fields=[
            'failed_attempts',
            'unknown_username_count',
            'blocked_at',
            'unlocked_at',
            'unlocked_by',
        ],
    )
