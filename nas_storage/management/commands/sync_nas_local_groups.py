from django.core.management.base import BaseCommand

from nas_storage.nas_acl_apply import NasAclApplyError
from nas_storage.nas_group_sync import sync_nas_local_group_members, sync_portal_users_preview


class Command(BaseCommand):
    help = 'Gán user local DSM vào nhóm phòng ban trên NAS (theo Portal + mô tả DSM).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ liệt kê user → nhóm, không gọi synogroup.',
        )
        parser.add_argument(
            '--preview',
            action='store_true',
            help='Chỉ xem map Portal → nhóm (không SSH).',
        )
        parser.add_argument(
            '--no-dsm-description',
            action='store_true',
            help='Không fallback mô tả user trên DSM (chỉ dùng phòng ban Portal).',
        )

    def handle(self, *args, **options):
        if options['preview']:
            for row in sync_portal_users_preview():
                self.stdout.write(
                    f'{row["username"]:20} {row["department"]:30} → {row["nas_group"]}'
                )
            return

        try:
            stats = sync_nas_local_group_members(
                dry_run=options['dry_run'],
                include_dsm_description=not options['no_dsm_description'],
            )
        except NasAclApplyError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry-run — kế hoạch gán nhóm:'))
            for line in stats.get('planned') or []:
                self.stdout.write(f'  {line}')
            return

        self.stdout.write(self.style.SUCCESS(f'Đã gán: {stats["assigned"]} user'))
        for err in stats.get('errors') or []:
            self.stderr.write(self.style.WARNING(err))
