from django.core.management.base import BaseCommand

from tools.services import warm_background_removal


class Command(BaseCommand):
    help = 'Tải sẵn mô hình xóa nền (rembg) — chạy sau deploy.'

    def handle(self, *args, **options):
        self.stdout.write('Đang tải mô hình u2net…')
        warm_background_removal()
        self.stdout.write(self.style.SUCCESS('Mô hình xóa nền đã sẵn sàng.'))
