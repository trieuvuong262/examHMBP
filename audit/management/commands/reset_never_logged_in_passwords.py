"""Đặt mật khẩu Portal (và đồng bộ Odoo) cho user chưa từng đăng nhập."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from audit.services.odoo_sync import (
    OdooSyncError,
    _execute,
    _portal_login,
    notify_portal_password_changed,
    odoo_configured,
    user_has_odoo_portal_access,
)
from hrm.models import Profile

DEFAULT_PASSWORD = 'justplay@123'
SKIP_USERNAMES = frozenset({'admin'})


def _push_odoo_password_by_login(login: str, password: str) -> bool:
    """Cập nhật mật khẩu Odoo theo login (không vô hiệu user)."""
    if not login or not odoo_configured():
        return False
    ids = _execute('res.users', 'search', [('login', '=', login)], limit=1)
    if not ids:
        return False
    _execute('res.users', 'write', [int(ids[0])], {'password': password, 'active': True})
    return True


class Command(BaseCommand):
    help = (
        'Đặt mật khẩu cho user Portal chưa từng đăng nhập (last_login IS NULL). '
        'User đã đăng nhập ít nhất một lần không bị đổi. Đồng bộ Odoo nếu có quyền ERP.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default=DEFAULT_PASSWORD,
            help=f'Mật khẩu mới (mặc định: {DEFAULT_PASSWORD})',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ liệt kê user sẽ đổi, không ghi DB/Odoo.',
        )

    def handle(self, *args, **options):
        password = (options['password'] or DEFAULT_PASSWORD).strip()
        dry_run = bool(options['dry_run'])

        qs = (
            User.objects.filter(is_active=True, last_login__isnull=True)
            .exclude(username__in=SKIP_USERNAMES)
            .select_related('profile')
            .order_by('username')
        )

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Không có user nào chưa từng đăng nhập.'))
            return

        self.stdout.write(f'Tìm thấy {total} user chưa đăng nhập (bỏ qua: {", ".join(sorted(SKIP_USERNAMES))})')
        if dry_run:
            for user in qs:
                login = _portal_login(user)
                odoo = 'odoo-menu' if user_has_odoo_portal_access(user) else 'odoo-login'
                self.stdout.write(f'  [dry-run] {user.username} ({odoo}: {login})')
            return

        updated = 0
        odoo_synced = 0
        errors = []

        for user in qs:
            login = _portal_login(user)
            try:
                user.set_password(password)
                user.save(update_fields=['password'])
                Profile.require_password_change(user)
                updated += 1

                profile = getattr(user, 'profile', None)
                if user_has_odoo_portal_access(user):
                    notify_portal_password_changed(user, password)
                    if profile:
                        profile.odoo_password_synced = True
                        profile.save(update_fields=['odoo_password_synced'])
                    odoo_synced += 1
                elif _push_odoo_password_by_login(login, password):
                    if profile:
                        profile.odoo_password_synced = True
                        profile.save(update_fields=['odoo_password_synced'])
                    odoo_synced += 1

                self.stdout.write(f'  OK {user.username}')
            except (OdooSyncError, Exception) as exc:
                errors.append(f'{user.username}: {exc}')
                self.stderr.write(self.style.ERROR(f'  LỖI {user.username}: {exc}'))

        self.stdout.write(self.style.SUCCESS(
            f'Hoàn tất: {updated}/{total} user đổi mật khẩu, {odoo_synced} đồng bộ Odoo.'
        ))
        for err in errors:
            self.stderr.write(self.style.WARNING(err))
