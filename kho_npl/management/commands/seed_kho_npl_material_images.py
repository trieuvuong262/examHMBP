"""
Tải ảnh demo cho danh mục NPL từ internet (Wikimedia Commons).

Usage:
    python manage.py seed_kho_npl_material_images
    python manage.py seed_kho_npl_material_images --limit 30
    python manage.py seed_kho_npl_material_images --force
    python manage.py seed_kho_npl_material_images --active-only
"""

from __future__ import annotations

import mimetypes
import time

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.models import Q

from kho_npl.material_demo_images import demo_image_urls_for_material
from kho_npl.models import Material

USER_AGENT = 'PortalJustPlay-NPL-Demo/1.0 (+https://portal.justplay.vn)'


def _ext_from_response(content_type: str | None, url: str) -> str:
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
        if ext in ('.jpe', '.jpeg'):
            return '.jpg'
        if ext:
            return ext
    if '.png' in url.lower():
        return '.png'
    if '.webp' in url.lower():
        return '.webp'
    return '.jpg'


def download_demo_image(url: str, timeout: int = 45) -> tuple[bytes, str]:
    resp = requests.get(
        url,
        timeout=timeout,
        headers={'User-Agent': USER_AGENT},
    )
    resp.raise_for_status()
    if not resp.content:
        raise ValueError('empty response body')
    ext = _ext_from_response(resp.headers.get('Content-Type'), url)
    return resp.content, ext


class Command(BaseCommand):
    help = 'Tải ảnh demo từ internet gán vào danh mục NPL (ưu tiên NPL chưa có ảnh).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Giới hạn số NPL (0 = tất cả trong queryset).',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Ghi đè ảnh đã có.',
        )
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='Chỉ NPL đang hoạt động.',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.15,
            help='Giây nghỉ giữa các lần tải (tránh spam).',
        )

    def handle(self, *args, **options):
        limit: int = options['limit']
        force: bool = options['force']
        active_only: bool = options['active_only']
        delay: float = options['delay']

        qs = Material.objects.select_related('category', 'category__parent').order_by('code')
        if active_only:
            qs = qs.filter(is_active=True)
        if not force:
            qs = qs.filter(Q(image='') | Q(image__isnull=True))

        materials = list(qs)
        if limit > 0:
            materials = materials[:limit]

        if not materials:
            self.stdout.write(self.style.WARNING('Không có NPL nào cần gán ảnh demo.'))
            return

        ok = 0
        failed: list[str] = []
        for idx, material in enumerate(materials, start=1):
            urls = demo_image_urls_for_material(material)
            saved = False
            last_err: Exception | None = None
            used_url = urls[0]
            for url in urls:
                try:
                    data, ext = download_demo_image(url)
                    filename = f'{material.code}{ext}'.lower().replace('/', '-')
                    if material.image and force:
                        material.image.delete(save=False)
                    material.image.save(filename, ContentFile(data), save=True)
                    ok += 1
                    saved = True
                    used_url = url
                    self.stdout.write(f'  [{idx}/{len(materials)}] {material.code} ← {url}')
                    break
                except Exception as exc:
                    last_err = exc
            if not saved:
                failed.append(f'{material.code}: {last_err}')
                self.stdout.write(self.style.ERROR(f'  FAIL {material.code}: {last_err}'))
            if delay and idx < len(materials):
                time.sleep(delay)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Đã gán ảnh demo: {ok}/{len(materials)} NPL.'))
        if failed:
            self.stdout.write(self.style.WARNING(f'Lỗi: {len(failed)} — xem log trên.'))
