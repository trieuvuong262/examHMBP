"""Dời đính kèm + ảnh inline của báo cáo VP kỳ Tuần/Tháng sang thư mục NAS riêng.

Trước đây mọi báo cáo VP (ngày/tuần/tháng) đều lưu chung ``BAO_CAO_NGAY``.
Lệnh này dời file của báo cáo kỳ Tuần → ``BAO_CAO_TUAN`` và kỳ Tháng →
``BAO_CAO_THANG``, đồng thời gắn tiền tố ``_tuan/`` / ``_thang/`` vào
``file.name`` và cập nhật URL ảnh inline trong ``document_html``.

An toàn để chạy lại (idempotent): file đã có tiền tố sẽ bỏ qua.
"""

from __future__ import annotations

import re
import subprocess

from django.core.management.base import BaseCommand
from django.db import transaction

from reports.daily_nas_storage import (
    OFFICE_MONTH_PREFIX,
    OFFICE_WEEK_PREFIX,
    daily_report_nas_rel_base,
    monthly_report_nas_rel_base,
)
from reports.models import DailyWorkReport
from reports.nas_pending import (
    KIND_DAILY,
    KIND_MONTH,
    KIND_WEEKLY,
    pending_exists,
    pending_path,
    remove_pending,
    write_pending,
)
from reports.report_profile import REPORT_PROFILE_OFFICE
from reports.weekly_nas_storage import weekly_report_nas_rel_base

# Rel ảnh inline chưa gắn tiền tố kỳ: {year}/{yyyy-mm-dd}/{user}/vanban/inline/{file}
_INLINE_REL_RE = re.compile(
    r'(?<![\w/])(\d{4}/\d{4}-\d{2}-\d{2}/[^/"\'?<>\s]+/vanban/inline/[^"\'?<>\s]+)'
)


def _rclone_env() -> dict:
    from nas_storage.nas_paths import _rclone_env as nas_rclone_env

    return nas_rclone_env()


def _bucket_for_period(period: str):
    if period == 'week':
        return OFFICE_WEEK_PREFIX, KIND_WEEKLY, weekly_report_nas_rel_base()
    return OFFICE_MONTH_PREFIX, KIND_MONTH, monthly_report_nas_rel_base()


class Command(BaseCommand):
    help = 'Dời file báo cáo VP kỳ Tuần/Tháng sang thư mục NAS riêng (BAO_CAO_TUAN/BAO_CAO_THANG).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Chỉ in kế hoạch, không thay đổi.')
        parser.add_argument('--report-id', type=int, default=None, help='Chỉ xử lý 1 báo cáo.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        self.dry = dry
        self.env = _rclone_env()
        self.daily_base = daily_report_nas_rel_base()

        qs = DailyWorkReport.objects.filter(
            report_profile=REPORT_PROFILE_OFFICE,
            report_period__in=('week', 'month'),
        ).order_by('id')
        if options['report_id']:
            qs = qs.filter(id=options['report_id'])

        moved_files = 0
        moved_inline = 0
        reports_touched = 0

        for report in qs.iterator():
            prefix, kind, target_base = _bucket_for_period(report.report_period)
            changed = False

            for att in report.attachments.all():
                name = att.file.name or ''
                if not name or name.startswith((OFFICE_WEEK_PREFIX, OFFICE_MONTH_PREFIX)):
                    continue
                if self._move_rel(name, target_base, kind):
                    if not dry:
                        att.file.name = f'{prefix}{name}'
                        att.save(update_fields=['file'])
                    moved_files += 1
                    changed = True

            html = report.document_html or ''
            if html:
                new_html, n = self._migrate_inline(html, prefix, target_base, kind)
                if n:
                    moved_inline += n
                    changed = True
                    if not dry and new_html != html:
                        report.document_html = new_html
                        DailyWorkReport.objects.filter(pk=report.pk).update(document_html=new_html)

            if changed:
                reports_touched += 1
                self.stdout.write(
                    f'  [{report.report_period}] report#{report.id} '
                    f'{report.employee.username} {report.report_date} → {target_base}'
                )

        verb = 'SẼ DỜI (dry-run)' if dry else 'ĐÃ DỜI'
        self.stdout.write(self.style.SUCCESS(
            f'{verb}: {moved_files} đính kèm + {moved_inline} ảnh inline '
            f'trên {reports_touched} báo cáo.'
        ))

    def _migrate_inline(self, html: str, prefix: str, target_base: str, kind: str):
        rels = []
        for m in _INLINE_REL_RE.finditer(html):
            rel = m.group(1)
            if rel not in rels:
                rels.append(rel)
        count = 0
        for rel in rels:
            if self._move_rel(rel, target_base, kind):
                html = html.replace(rel, f'{prefix}{rel}')
                count += 1
        return html, count

    def _move_rel(self, rel: str, target_base: str, kind: str) -> bool:
        """Dời 1 file NAS/pending từ BAO_CAO_NGAY sang thư mục đích. True nếu có dời."""
        # 1) Bản tạm trên VPS (chưa lên NAS) → chuyển sang bucket pending đúng kỳ
        if pending_exists(KIND_DAILY, rel):
            if not self.dry:
                src = pending_path(KIND_DAILY, rel)
                write_pending(kind, rel, src)
                remove_pending(KIND_DAILY, rel)
            return True

        # 2) File đã trên NAS → rclone moveto (server-side, cùng remote)
        from nas_storage.nas_paths import app_storage_rclone_target

        src_target = app_storage_rclone_target(self.daily_base, rel)
        dst_target = app_storage_rclone_target(target_base, rel)
        if self.dry:
            # Đếm: có ở nguồn hoặc đã nằm ở đích (chạy lại sau lỗi)
            return self._rclone_exists(src_target) or self._rclone_exists(dst_target)

        # Đã dời sẵn ở lần chạy trước (DB chưa cập nhật) → chỉ cần cập nhật DB
        if self._rclone_exists(dst_target):
            return True
        if not self._rclone_exists(src_target):
            self.stderr.write(self.style.WARNING(f'    ! Bỏ qua {rel}: không thấy file ở NAS.'))
            return False
        try:
            self._rclone_moveto(src_target, dst_target)
            return True
        except OSError as exc:
            self.stderr.write(self.style.WARNING(f'    ! Không dời được {rel}: {exc}'))
            return False

    def _rclone_moveto(self, src_target: str, dst_target: str) -> None:
        proc = subprocess.run(
            ['rclone', 'moveto', src_target, dst_target],
            capture_output=True, text=True, timeout=600, check=False, env=self.env,
        )
        if proc.returncode != 0:
            raise OSError((proc.stderr or proc.stdout or '').strip()[:200])

    def _rclone_exists(self, target: str) -> bool:
        proc = subprocess.run(
            ['rclone', 'lsf', target],
            capture_output=True, text=True, timeout=120, check=False, env=self.env,
        )
        return proc.returncode == 0 and bool((proc.stdout or '').strip())
