from django.core.management.base import BaseCommand

from audit.services.odoo_sync import OdooSyncError, sync_all_odoo_users


class Command(BaseCommand):
    help = 'Đồng bộ tài khoản Portal có quyền Odoo sang ERP (res.users).'

    def handle(self, *args, **options):
        try:
            stats = sync_all_odoo_users()
        except OdooSyncError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Odoo sync: ok={stats["ok"]}, deactivated={stats["deactivated"]}, skipped={stats["skipped"]}'
        ))
        for err in stats.get('errors') or []:
            self.stderr.write(self.style.WARNING(err))
