from django.core.management.base import BaseCommand

from audit.services.nas_ldap_sync import NasLdapSyncError, ensure_department_groups, sync_all_nas_ldap_users


class Command(BaseCommand):
    help = 'Đồng bộ nhân viên Portal sang Synology LDAP (user + group phòng ban).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--groups-only',
            action='store_true',
            help='Chỉ tạo group phòng ban trên LDAP, không đồng bộ user.',
        )
        parser.add_argument(
            '--password',
            default='',
            help='Đặt cùng mật khẩu cho mọi user LDAP (tùy chọn — bulk reset).',
        )

    def handle(self, *args, **options):
        if options['groups_only']:
            try:
                created = ensure_department_groups()
            except NasLdapSyncError as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                return
            if created:
                self.stdout.write(self.style.SUCCESS(f'Đã tạo group LDAP: {", ".join(created)}'))
            else:
                self.stdout.write(self.style.SUCCESS('Group phòng ban LDAP đã đủ.'))
            return

        password = (options['password'] or '').strip() or None
        try:
            stats = sync_all_nas_ldap_users(password=password)
        except NasLdapSyncError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        if stats.get('groups_created'):
            self.stdout.write(f'Group mới: {", ".join(stats["groups_created"])}')
        self.stdout.write(self.style.SUCCESS(
            f'NAS LDAP sync: ok={stats["ok"]}, skipped={stats["skipped"]}'
        ))
        for err in stats.get('errors') or []:
            self.stderr.write(self.style.WARNING(err))
