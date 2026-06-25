"""Bật cờ bắt buộc đổi mật khẩu lần đăng nhập tiếp theo (không đổi MK)."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from hrm.models import Profile

SKIP_USERNAMES = frozenset({'admin', 'ductn', 'vuonglnt'})


class Command(BaseCommand):
    help = 'Đặt must_change_password=True cho user active (trừ admin, Ductn, Vuonglnt).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        users = User.objects.filter(is_active=True).order_by('username')
        targets = [u for u in users if u.username.lower() not in SKIP_USERNAMES]
        if options['dry_run']:
            self.stdout.write(f'Sẽ bật cờ cho {len(targets)} user.')
            return
        count = 0
        for user in targets:
            Profile.require_password_change(user)
            count += 1
        self.stdout.write(self.style.SUCCESS(f'OK: must_change_password enabled for {count} users.'))
