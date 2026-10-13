"""Đồng bộ file báo cáo lưu tạm trên VPS lên NAS (chạy định kỳ hoặc thủ công)."""

from django.core.management.base import BaseCommand

from recruitment.cv_nas_storage import count_pending_cv
from reports.nas_pending import count_pending
from reports.nas_pending_sync import sync_all_pending


class Command(BaseCommand):
    help = 'Đẩy file báo cáo và CV đang lưu tạm trên VPS lên NAS rồi xóa bản tạm.'

    def handle(self, *args, **options):
        pending = count_pending() + count_pending_cv()
        if not pending:
            self.stdout.write(self.style.SUCCESS('Không có file nào chờ đồng bộ.'))
            return

        self.stdout.write(f'Có {pending} file chờ đồng bộ lên NAS...')
        stats = sync_all_pending()

        if stats['status'] == 'nas_down':
            self.stderr.write(self.style.WARNING(
                f'NAS chưa sẵn sàng — đã đồng bộ {stats["synced"]}, '
                f'còn {count_pending() + count_pending_cv()} file chờ.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Đã đồng bộ {stats["synced"]} file lên NAS.'
            ))
        for err in stats.get('errors') or []:
            self.stderr.write(self.style.WARNING(err))
