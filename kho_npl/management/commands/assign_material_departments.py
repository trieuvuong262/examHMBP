from django.core.management.base import BaseCommand

from kho_npl.material_department import assign_default_departments


class Command(BaseCommand):
    help = 'Gán bộ phận mặc định cho NPL theo nhóm (chuẩn HR SX/QLCL).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Ghi đè cả mã đã có bộ phận (mặc định chỉ gán ô trống).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ thống kê, không ghi DB.',
        )

    def handle(self, *args, **options):
        result = assign_default_departments(
            only_blank=not options['all'],
            dry_run=options['dry_run'],
        )
        mode = 'dry-run' if result['dry_run'] else 'updated'
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] matched={result['matched']} updated={result['updated']}"
            )
        )
        for label, count in result['by_department'].items():
            self.stdout.write(f'  {label}: {count}')
