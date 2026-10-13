"""Gắn lại bộ phận lộ trình theo công đoạn trên OB và đơn hàng."""

from django.core.management.base import BaseCommand

from san_xuat.services.capacity_from_hrm import align_route_departments
from san_xuat.services.team_division_map import assign_division_progress_slugs


class Command(BaseCommand):
    help = 'Gắn bộ phận OB, đơn và lộ trình theo công đoạn — không gộp hai bộ phận trên một dòng.'

    def handle(self, *args, **options):
        mapped = assign_division_progress_slugs()
        self.stdout.write(f'Map bộ phận HR → tổ Tiến độ: {mapped} dòng chuyển sang mã riêng.')
        stats = align_route_departments()
        self.stdout.write(
            'OB cập nhật {ob_updated}, giữ {ob_skipped}, chưa khớp {ob_unresolved}. '
            'Đơn cập nhật {order_updated}, giữ {order_skipped}, chưa khớp {order_unresolved}. '
            'Bước kế hoạch {plan_updated}. Phân bổ ngày {day_moved}.'.format(**stats)
        )
