"""Gắn lại bộ phận lộ trình theo công đoạn trên OB và đơn hàng."""

from django.core.management.base import BaseCommand

from san_xuat.services.capacity_from_hrm import align_route_departments


class Command(BaseCommand):
    help = 'Gắn bộ phận OB, đơn và lộ trình theo công đoạn — không gộp hai bộ phận trên một dòng.'

    def handle(self, *args, **options):
        stats = align_route_departments()
        self.stdout.write(
            'OB cập nhật {ob_updated}, giữ {ob_skipped}, chưa khớp {ob_unresolved}. '
            'Đơn cập nhật {order_updated}, giữ {order_skipped}, chưa khớp {order_unresolved}. '
            'Bước kế hoạch {plan_updated}. Phân bổ ngày {day_moved}.'.format(**stats)
        )
