"""
Cập nhật nội dung hướng dẫn trong DB từ template mẫu (có ảnh PNG mới).

Usage:
    python manage.py sync_guide_content
    python manage.py sync_guide_content --force
"""

from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from hrm.models import UserGuide


class Command(BaseCommand):
    help = 'Đồng bộ nội dung hướng dẫn từ template mẫu (ảnh chụp portal mới).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Ghi đè cả khi đã có nội dung tùy chỉnh.',
        )

    def handle(self, *args, **options):
        guide = UserGuide.load()
        if guide.has_content and not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    'Hướng dẫn đã có nội dung trong DB. '
                    'Dùng --force để ghi đè bằng bản mẫu mới.'
                )
            )
            return

        body = render_to_string('guide/_default_body.html', request=None)
        if not strip_tags(body).strip():
            self.stderr.write('Template mẫu trống.')
            return

        guide.title = guide.title or 'Hướng dẫn sử dụng JustPlay Portal'
        guide.body = body
        guide.save(update_fields=['title', 'body', 'updated_at'])
        self.stdout.write(self.style.SUCCESS('Đã đồng bộ hướng dẫn từ template mẫu (ảnh PNG).'))
