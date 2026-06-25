from django.core.management.base import BaseCommand

from nas_storage.nas_acl_apply import NasAclApplyError, apply_all_folder_permissions
from nas_storage.seed_nas_permissions import seed_nas_permissions


class Command(BaseCommand):
    help = 'Tạo nhóm NAS, share phòng ban và quyền RW mặc định trên Portal (theo dept_nas_config).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ mô phỏng, không ghi DB.',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Sau khi seed, áp dụng ACL lên NAS qua SSH (cần NAS_SSH_*).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        stats = seed_nas_permissions(dry_run=dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry-run — không ghi DB.'))

        self.stdout.write(
            f'Nhóm: +{stats["groups_created"]} / cập nhật {stats["groups_updated"]}'
        )
        self.stdout.write(
            f'Share: +{stats["folders_created"]} / cập nhật {stats["folders_updated"]}'
        )
        self.stdout.write(
            f'Quyền: +{stats["permissions_created"]} / cập nhật {stats["permissions_updated"]}'
        )

        if options['apply'] and not dry_run:
            try:
                result = apply_all_folder_permissions()
            except NasAclApplyError as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                return
            self.stdout.write(self.style.SUCCESS(f'Áp dụng NAS: ok={result["ok"]}, skipped={result["skipped"]}'))
            for err in result.get('errors') or []:
                self.stderr.write(self.style.WARNING(err))
        elif options['apply'] and dry_run:
            self.stdout.write(self.style.WARNING('Bỏ qua --apply trong dry-run.'))

        self.stdout.write(self.style.SUCCESS('Seed NAS permissions xong.'))
