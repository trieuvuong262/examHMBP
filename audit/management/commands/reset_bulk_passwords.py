"""Reset mật khẩu Portal + đồng bộ Odoo (bulk) — trừ danh sách loại."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from audit.services.odoo_sync import OdooSyncError, provision_erp_user
from hrm.models import Profile

DEFAULT_PASSWORD = 'justplay@123'
# User giữ nguyên mật khẩu (so khớp không phân biệt hoa thường)
SKIP_USERNAMES = frozenset({'admin', 'ductn', 'vuonglnt'})


class Command(BaseCommand):
    help = (
        'Đặt mật khẩu Portal và đồng bộ Odoo cho mọi user active (trừ Ductn, Vuonglnt, admin). '
        'NV đang làm việc được tạo/cập nhật tài khoản ERP.'
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
            help='Chỉ liệt kê, không ghi DB/Odoo.',
        )

    def _should_skip(self, username: str) -> bool:
        return (username or '').strip().lower() in SKIP_USERNAMES

    def handle(self, *args, **options):
        password = (options['password'] or DEFAULT_PASSWORD).strip()
        dry_run = bool(options['dry_run'])

        users = (
            User.objects.filter(is_active=True)
            .select_related('profile')
            .order_by('username')
        )
        targets = [u for u in users if not self._should_skip(u.username)]
        skipped = [u.username for u in users if self._should_skip(u.username)]

        self.stdout.write(
            f'Target: {len(targets)} user | Giữ nguyên: {", ".join(sorted(skipped)) or "—"}'
        )

        if dry_run:
            for user in targets:
                profile = getattr(user, 'profile', None)
                employed = bool(profile and profile.is_employed)
                self.stdout.write(
                    f'  [dry-run] {user.username} (employed={employed})'
                )
            return

        portal_ok = 0
        odoo_ok = 0
        odoo_skip = 0
        errors = []

        for user in targets:
            try:
                user.set_password(password)
                user.save(update_fields=['password'])
                Profile.require_password_change(user)
                portal_ok += 1

                result = provision_erp_user(user, password=password)
                status = result.get('status')
                if status == 'ok':
                    odoo_ok += 1
                    tag = 'created' if result.get('created') else 'updated'
                    self.stdout.write(f'  OK {user.username} (portal + odoo {tag})')
                else:
                    odoo_skip += 1
                    reason = result.get('reason', status)
                    self.stdout.write(f'  OK {user.username} (portal only — odoo: {reason})')
            except OdooSyncError as exc:
                errors.append(f'{user.username}: {exc}')
                self.stderr.write(self.style.ERROR(f'  LỖI {user.username}: {exc}'))
            except Exception as exc:
                errors.append(f'{user.username}: {exc}')
                self.stderr.write(self.style.ERROR(f'  LỖI {user.username}: {exc}'))

        self.stdout.write(self.style.SUCCESS(
            f'Hoàn tất: {portal_ok} Portal, {odoo_ok} Odoo, {odoo_skip} bỏ qua Odoo.'
        ))
        for err in errors:
            self.stderr.write(self.style.WARNING(err))
