"""Smoke test các tính năng Kho NPL đã triển khai gần đây."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from django.core.management.base import BaseCommand

from kho_npl.choices import DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.models import Material, MaterialCategory, MaterialColor, MaterialSpecification
from kho_npl.models import StockDisposal, StockIssue, StockReceipt


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
        groups = MaterialCategory.objects.filter(is_active=True).count()
        self.stdout.write(
            f'  Mau sac: {color_count} | Quy cach: {spec_count} | Nhom: {groups}'
        )
        if color_count < 50:
            errors.append(f'Màu sắc thiếu (có {color_count}, cần >= 50).')
        if spec_count < 40:
            errors.append(f'Quy cách thiếu (có {spec_count}, cần >= 40).')
        if groups < 9:
            errors.append(f'Nhóm NPL thiếu (có {groups}, cần >= 9).')

        categorized = Material.objects.filter(is_active=True, category__isnull=False).count()
        self.stdout.write(f'  NPL gan nhom: {categorized}')

        if not user:
            self._finish(errors)
            return

        client = Client()
        client.force_login(user)
        host = 'portal.justplay.vn'
        for candidate in (getattr(settings, 'ALLOWED_HOSTS', None) or []):
            if candidate and candidate not in ('*', 'localhost', '127.0.0.1', 'testserver'):
                host = candidate
                break
        extra = {'HTTP_HOST': host}

        pages = [
            ('Danh mục', reverse('kho_npl:material_list'), [
                'data-col="category"', 'jp-npl-catalog-row', 'jp-npl-color-swatch', 'Nhóm',
            ]),
            ('Tồn kho', reverse('kho_npl:material_stock'), [
                'npl-stock-table', 'jp-npl-stock-row', 'data-col="image"', 'data-col="code"',
                'data-col="stock_status"', 'Đang tải chi tiết tồn kho', 'jp-npl-stock-detail-btn',
                'data-col="category"', 'Nhóm',
            ]),
            ('Phieu nhap', reverse('kho_npl:receipt_list'), ['npl-receipt-table', 'jp-npl-catalog-row']),
            ('Phieu xuat', reverse('kho_npl:issue_list'), ['npl-issue-table', 'jp-npl-catalog-row']),
            ('Phieu huy', reverse('kho_npl:disposal_list'), ['npl-disposal-table', 'jp-npl-catalog-row', 'jp-mat-edit-btn']),
            ('Kiem ke', reverse('kho_npl:adjustment_list'), ['npl-adjustment-table', 'jp-npl-catalog-row', 'jp-mat-edit-btn']),
            ('Thiet lap mau', reverse('kho_npl:settings_list', kwargs={'section': 'mau'}), ['jp-npl-color-swatch', 'Mã hex']),
            ('Thiết lập quy cách', reverse('kho_npl:settings_list', kwargs={'section': 'quy-cach'}), ['Quy cách']),
            ('Thiết lập nhóm', reverse('kho_npl:settings_list', kwargs={'section': 'nhom'}), ['Tên nhóm']),
        ]

        for label, url, needles in pages:
            resp = client.get(url, **extra)
            if resp.status_code != 200:
                errors.append(f'{label}: HTTP {resp.status_code} ({url})')
                continue
            html = resp.content.decode('utf-8', errors='replace')
            for needle in needles:
                if needle == 'jp-mat-edit-btn' and needle not in html:
                    # Icon chi hien khi co phieu nhap/xuat/huy/kiem ke duoc sua
                    if label == 'Phieu nhap' and not StockReceipt.objects.filter(status=DOC_STATUS_DRAFT).exists():
                        continue
                    if label == 'Phieu xuat' and not StockIssue.objects.filter(status=DOC_STATUS_DRAFT).exists():
                        continue
                    if label == 'Phieu huy' and not StockDisposal.objects.filter(status=DOC_STATUS_DRAFT).exists():
                        continue
                    if label == 'Kiem ke':
                        from kho_npl.choices import ADJUST_STATUS_PENDING
                        from kho_npl.models import StockAdjustment
                        if not StockAdjustment.objects.filter(status=ADJUST_STATUS_PENDING).exists():
                            continue
                if needle not in html:
                    errors.append(f'{label}: thieu "{needle}" trong HTML')

        # Ghi chú phiếu xuất đã ghi sổ
        issue = StockIssue.objects.filter(status=DOC_STATUS_POSTED).prefetch_related('lines').order_by('-pk').first()
        if issue:
            url = reverse('kho_npl:issue_update_notes', kwargs={'pk': issue.pk})
            resp = client.post(url, {'notes': 'Smoke test ghi chu'}, follow=True, **extra)
            if resp.status_code != 200:
                errors.append(f'Ghi chú phiếu xuất: HTTP {resp.status_code}')
            issue.refresh_from_db()
            if issue.notes != 'Smoke test ghi chu':
                errors.append('Ghi chú phiếu xuất: không lưu được notes')
            else:
                self.stdout.write(f'  Ghi chú phiếu xuất #{issue.pk}: OK')

            line = issue.lines.first()
            if line:
                line_url = reverse('kho_npl:issue_update_line_notes', kwargs={'pk': issue.pk})
                line_payload = {
                    'lines-TOTAL_FORMS': issue.lines.count(),
                    'lines-INITIAL_FORMS': issue.lines.count(),
                    'lines-MIN_NUM_FORMS': 0,
                    'lines-MAX_NUM_FORMS': 1000,
                }
                for idx, row in enumerate(issue.lines.order_by('pk')):
                    line_payload[f'lines-{idx}-id'] = row.pk
                    line_payload[f'lines-{idx}-notes'] = (
                        'Smoke ghi chu dong' if row.pk == line.pk else (row.notes or '')
                    )
                lresp = client.post(line_url, line_payload, follow=True, **extra)
                if lresp.status_code != 200:
                    errors.append(f'Ghi chú dòng phiếu xuất: HTTP {lresp.status_code}')
                line.refresh_from_db()
                if line.notes != 'Smoke ghi chu dong':
                    errors.append('Ghi chú dòng phiếu xuất: không lưu được notes')
                else:
                    self.stdout.write(f'  Ghi chú dòng phiếu xuất #{issue.pk}: OK')
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
