"""Nạp danh sách kho thành phẩm từ ``choices.DEFAULT_WAREHOUSES``.

Mặc định chỉ xem trước. Thêm ``--apply`` để ghi DB.
Chạy lại được nhiều lần: kho đã có thì chỉ cập nhật tên và hệ sở hữu, không tạo trùng.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from kho_san_pham.choices import DEFAULT_WAREHOUSES
from kho_san_pham.models import Warehouse


class Command(BaseCommand):
    help = 'Nạp danh sách kho thành phẩm. Mặc định xem trước; dùng --apply để ghi DB.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Ghi DB (mặc định chỉ xem trước).',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        created: list[str] = []
        updated: list[str] = []
        unchanged: list[str] = []

        with transaction.atomic():
            for code, name, owner_system in DEFAULT_WAREHOUSES:
                warehouse = Warehouse.objects.filter(code=code).first()
                if warehouse is None:
                    Warehouse.objects.create(code=code, name=name, owner_system=owner_system)
                    created.append(f'{code} — {name} [{owner_system}]')
                    continue

                changes = []
                if warehouse.name != name:
                    changes.append(f'tên: {warehouse.name!r} -> {name!r}')
                    warehouse.name = name
                if warehouse.owner_system != owner_system:
                    changes.append(f'hệ: {warehouse.owner_system} -> {owner_system}')
                    warehouse.owner_system = owner_system

                if changes:
                    warehouse.save(update_fields=['name', 'owner_system', 'updated_at'])
                    updated.append(f'{code} ({", ".join(changes)})')
                else:
                    unchanged.append(code)

            if not apply:
                transaction.set_rollback(True)

        for title, items in (
            ('Tạo mới', created),
            ('Cập nhật', updated),
            ('Không đổi', unchanged),
        ):
            self.stdout.write(f'{title}: {len(items)}')
            for item in items:
                self.stdout.write(f'  - {item}')

        extra = Warehouse.objects.exclude(
            code__in=[code for code, _, _ in DEFAULT_WAREHOUSES]
        ).values_list('code', flat=True)
        if extra:
            self.stdout.write(
                self.style.WARNING(
                    f'Kho có trong DB nhưng không có trong DEFAULT_WAREHOUSES: {", ".join(extra)} '
                    '(command không xóa — kiểm tra xem có phải kho tạo tay không).'
                )
            )

        if not apply:
            self.stdout.write(self.style.WARNING('\nXem trước — chưa ghi gì. Thêm --apply để ghi DB.'))
