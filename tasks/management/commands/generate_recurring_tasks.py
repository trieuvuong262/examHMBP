from django.core.management.base import BaseCommand

from tasks.recurrence_utils import process_due_recurrences


class Command(BaseCommand):
    help = 'Tạo công việc cá nhân lặp theo chu kỳ (chạy hàng ngày qua cron).'

    def handle(self, *args, **options):
        created = process_due_recurrences()
        self.stdout.write(self.style.SUCCESS(f'Đã tạo {created} công việc lặp.'))
