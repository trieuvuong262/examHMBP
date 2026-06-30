"""Smoke test các tính năng Kho NPL đã triển khai gần đây."""

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from django.core.management.base import BaseCommand

from kho_npl.models import Material, MaterialCategory, MaterialColor, MaterialSpecification, StockIssue
from kho_npl.choices import DOC_STATUS_POSTED


class Command(BaseCommand):
    help = 'Smoke test workflow Kho NPL (màu, quy cách, nhóm 2 cấp, ghi chú phiếu xuất, UI danh sách).'

    def handle(self, *args, **options):
        errors = []
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
        if not user:
            errors.append('Không tìm thấy user admin/staff để test HTTP.')
            user = None

        # Master data
        color_count = MaterialColor.objects.filter(is_active=True).count()
        spec_count = MaterialSpecification.objects.filter(is_active=True).count()
        roots = MaterialCategory.objects.filter(is_active=True, parent__isnull=True).count()
        leaves = MaterialCategory.objects.filter(is_active=True, parent__isnull=False).count()
        self.stdout.write(f'  Màu sắc: {color_count} | Quy cách: {spec_count} | Nhóm cha: {roots} | Nhóm con: {leaves}')
        if color_count < 50:
            errors.append(f'Màu sắc thiếu (có {color_count}, cần >= 50).')
        if spec_count < 40:
            errors.append(f'Quy cách thiếu (có {spec_count}, cần >= 40).')
        if roots < 7:
            errors.append(f'Nhóm cha thiếu (có {roots}, cần >= 7).')
        if leaves < 9:
            errors.append(f'Nhóm con thiếu (có {leaves}, cần >= 9).')

        mat_with_parent = Material.objects.filter(
            is_active=True, category__parent__isnull=False,
        ).count()
        self.stdout.write(f'  NPL gắn nhóm con: {mat_with_parent}')
        if mat_with_parent == 0 and Material.objects.exists():
            errors.append('Có NPL nhưng chưa gắn nhóm con (cấp 2).')

        if not user:
            self._finish(errors)
            return

        client = Client()
        client.force_login(user)

        pages = [
            ('Danh mục', reverse('kho_npl:material_list'), [
                'data-col="category_parent"', 'bi-pencil', 'jp-npl-color-swatch',
                'Nhóm cha', 'Nhóm con', '<optgroup',
            ]),
            ('Tồn kho', reverse('kho_npl:material_stock'), [
                'data-col="category_parent"', 'Nhóm cha', '<optgroup',
            ]),
            ('Phiếu nhập', reverse('kho_npl:receipt_list'), ['bi-pencil', 'jp-mat-edit-btn']),
            ('Phiếu xuất', reverse('kho_npl:issue_list'), ['bi-pencil']),
            ('Phiếu hủy', reverse('kho_npl:disposal_list'), ['bi-pencil']),
            ('Kiểm kê', reverse('kho_npl:stocktake_list'), ['bi-pencil']),
            ('Thiết lập màu', reverse('kho_npl:settings_list', kwargs={'section': 'mau'}), ['bi-palette', 'jp-npl-color-swatch']),
            ('Thiết lập quy cách', reverse('kho_npl:settings_list', kwargs={'section': 'quy-cach'}), ['Quy cách']),
            ('Thiết lập nhóm', reverse('kho_npl:settings_list', kwargs={'section': 'nhom'}), ['Nhóm cha']),
        ]

        for label, url, needles in pages:
            resp = client.get(url)
            if resp.status_code != 200:
                errors.append(f'{label}: HTTP {resp.status_code} ({url})')
                continue
            html = resp.content.decode('utf-8', errors='replace')
            for needle in needles:
                if needle not in html:
                    errors.append(f'{label}: thiếu "{needle}" trong HTML')

        # Ghi chú phiếu xuất đã ghi sổ
        issue = StockIssue.objects.filter(status=DOC_STATUS_POSTED).order_by('-pk').first()
        if issue:
            url = reverse('kho_npl:issue_update_notes', kwargs={'pk': issue.pk})
            resp = client.post(url, {'notes': 'Smoke test ghi chú'}, follow=True)
            if resp.status_code != 200:
                errors.append(f'Ghi chú phiếu xuất: HTTP {resp.status_code}')
            issue.refresh_from_db()
            if issue.notes != 'Smoke test ghi chú':
                errors.append('Ghi chú phiếu xuất: không lưu được notes')
            else:
                self.stdout.write(f'  Ghi chú phiếu xuất #{issue.pk}: OK')
        else:
            self.stdout.write(self.style.WARNING('  Bỏ qua test ghi chú — chưa có phiếu xuất đã ghi sổ.'))

        self._finish(errors)

    def _finish(self, errors):
        if errors:
            self.stdout.write(self.style.ERROR(f'FAIL — {len(errors)} lỗi:'))
            for err in errors:
                self.stdout.write(self.style.ERROR(f'  - {err}'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('PASS — smoke test Kho NPL OK.'))
