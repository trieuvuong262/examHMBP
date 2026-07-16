"""
Tạo dữ liệu demo module Sản xuất — toàn bộ menu hub (trừ kho SP / kho NPL).

Usage:
    python manage.py seed_san_xuat_demo
    python manage.py seed_san_xuat_demo --clear
    python manage.py seed_san_xuat_demo --adopt --codes SP008073
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from san_xuat.services.bom import BomError
from san_xuat.services.demo_seed import (
    DEMO_NOTE_PREFIX,
    clear_all_san_xuat_demo,
    discover_kv_product_codes,
    seed_demo_tech_doc,
)
from san_xuat.services.demo_seed_hub import seed_demo_hub


class Command(BaseCommand):
    help = (
        'Tạo demo Sản xuất: hồ sơ/BOM + kế hoạch + điều phối + QC + giá thành KH. '
        'Không tạo dữ liệu kho sản phẩm hay kho nguyên phụ liệu.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help=f'Xóa toàn bộ dữ liệu demo Sản xuất ({DEMO_NOTE_PREFIX} / is_demo).',
        )
        parser.add_argument(
            '--codes',
            default='',
            help='Danh sách mã SP, phân tách dấu phẩy. Mặc định: tự chọn từ mirror KV.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='Số hồ sơ SX tối đa (mặc định 5).',
        )
        parser.add_argument(
            '--user',
            default='admin',
            help='Username ghi nhận người tạo (mặc định: admin).',
        )
        parser.add_argument(
            '--no-activate',
            action='store_true',
            help='Không kích hoạt BOM sau khi seed.',
        )
        parser.add_argument(
            '--no-costing',
            action='store_true',
            help='Không lưu bản chốt costing hồ sơ.',
        )
        parser.add_argument(
            '--adopt',
            action='store_true',
            help='Gắn nhãn demo cho hồ sơ đã tồn tại (vd. pilot SP008073).',
        )
        parser.add_argument(
            '--force-lines',
            action='store_true',
            help='Xóa dòng BOM/công đoạn demo rồi ghi lại mẫu.',
        )
        parser.add_argument(
            '--hub-only',
            action='store_true',
            help='Chỉ seed menu hub (bỏ qua hồ sơ SX).',
        )
        parser.add_argument(
            '--docs-only',
            action='store_true',
            help='Chỉ seed hồ sơ SX / BOM.',
        )

    def handle(self, *args, **options):
        if options['clear']:
            counts = clear_all_san_xuat_demo()
            self.stdout.write(self.style.SUCCESS(
                f'Đã xóa demo: hub={counts["hub"]}, hồ sơ={counts["tech_docs"]}.',
            ))
            return

        user = self._resolve_user(options['user'])
        codes = self._resolve_codes(options)
        if not codes:
            raise CommandError(
                'Không tìm thấy mã SP trên mirror KiotViet. '
                'Truyền --codes SP008073 hoặc sync KiotViet trước.',
            )

        activate = not options['no_activate']
        costing = not options['no_costing']
        seed_docs = not options['hub_only']
        seed_hub = not options['docs_only']

        created = updated = skipped = 0
        doc_links: list[str] = []

        with transaction.atomic():
            if seed_docs:
                for code in codes:
                    try:
                        doc, bom, stats = seed_demo_tech_doc(
                            code,
                            user=user,
                            activate=activate,
                            costing=costing,
                            force_lines=options['force_lines'],
                            adopt_existing=options['adopt'],
                        )
                    except BomError as exc:
                        self.stdout.write(self.style.WARNING(str(exc)))
                        skipped += 1
                        continue

                    if stats['created']:
                        created += 1
                        self.stdout.write(self.style.SUCCESS(f'+ Hồ sơ {code} #{doc.pk}'))
                    else:
                        updated += 1
                        self.stdout.write(f'~ Hồ sơ {code} #{doc.pk}')

                    self.stdout.write(
                        f'  BOM: {stats["bom_lines"]} NVL, {stats["process_steps"]} công đoạn'
                        + (', costing OK' if stats['costing_saved'] else '')
                    )
                    doc_links.append(f'/san-xuat/ho-so/{doc.pk}/')

            if seed_hub:
                hub_stats = seed_demo_hub(product_codes=codes, user=user)
                self.stdout.write(self.style.SUCCESS('Hub demo:'))
                for key, val in sorted(hub_stats.items()):
                    self.stdout.write(f'  {key}: {val}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Hồ sơ: {created} tạo, {updated} cập nhật, {skipped} bỏ qua.',
        ))
        if doc_links:
            self.stdout.write('Hồ sơ SX:')
            for link in doc_links:
                self.stdout.write(f'  {link}')
        self.stdout.write('Menu demo: /san-xuat/ke-hoach/, /dieu-phoi/, /chat-luong/, /gia-thanh/')
        self.stdout.write('Không tạo dữ liệu kho sản phẩm / kho nguyên phụ liệu.')

    def _resolve_user(self, username: str):
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if not user:
            raise CommandError(f'Không tìm thấy user: {username}')
        return user

    def _resolve_codes(self, options) -> list[str]:
        raw = (options['codes'] or '').strip()
        if raw:
            return [c.strip() for c in raw.split(',') if c.strip()][: max(1, options['limit'])]
        return discover_kv_product_codes(limit=max(1, options['limit']))
