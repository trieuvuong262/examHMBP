"""Gộp báo cáo ca tối bị nhầm (thực chất tăng ca ca sáng) vào ca sáng.

Nhận diện: cùng NV + cùng ngày có cả MORNING và NIGHT, và ca tối không có
sản lượng / thời gian sau 23h (slot qua đêm 23h–5h).

Chạy thử:
  python manage.py fix_misclassified_night_ot --date 2026-07-10
  python manage.py fix_misclassified_night_ot --from 2026-07-01 --to 2026-07-10

Áp dụng:
  python manage.py fix_misclassified_night_ot --date 2026-07-10 --apply
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from reports.models import (
    DailyWorkReport,
    ProductionHourlyQuantity,
    ProductionShiftProduct,
    ReportComment,
)
from reports.production_slots import MORNING_SLOTS, NIGHT_SLOTS
from reports.report_profile import REPORT_PROFILE_PRODUCTION

# Ca tối slot 0–5 = 17h–23h ↔ ca sáng tăng ca slot 8–13
_NIGHT_TO_MORNING_SLOT = {
    night.index: morning.index
    for night, morning in zip(NIGHT_SLOTS[:6], MORNING_SLOTS[8:14])
}
_OVERNIGHT_NIGHT_SLOTS = {s.index for s in NIGHT_SLOTS if s.index >= 6}


def _parse_date(value: str):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise CommandError(f'Ngày không hợp lệ: {value} (YYYY-MM-DD)') from exc


def _local(dt):
    if dt is None:
        return None
    return timezone.localtime(dt) if timezone.is_aware(dt) else timezone.make_aware(dt)


def is_misclassified_morning_overtime(night: DailyWorkReport, morning: DailyWorkReport) -> bool:
    """Ca tối chỉ có dữ liệu trong khung tăng ca 17h–23h (không qua đêm)."""
    if not morning or not night:
        return False
    products = list(night.production_products.all())
    if not products:
        return True

    report_day = night.report_date
    next_day = report_day + timedelta(days=1)

    for product in products:
        for entry in product.hourly_entries.all():
            qty = entry.quantity or 0
            dmg = entry.damaged_quantity or 0
            if entry.slot_index in _OVERNIGHT_NIGHT_SLOTS and (qty or dmg):
                return False
        for ts in (product.started_at, product.ended_at):
            local = _local(ts)
            if not local:
                continue
            # Sau nửa đêm của ngày báo cáo → ca tối thật
            if local.date() >= next_day:
                return False
            # Cùng ngày nhưng từ 23h trở đi và có slot qua đêm đã chặn ở trên;
            # nếu started sau 23h vẫn có thể là tăng ca sát giờ — cho phép nếu không có slot overnight
            if local.date() == report_day and local.time() >= time(23, 0):
                # Chỉ coi là ca tối thật nếu có entry overnight; không thì vẫn OT
                pass
    return True


def _remap_slot(night_slot: int) -> int | None:
    if night_slot in _NIGHT_TO_MORNING_SLOT:
        return _NIGHT_TO_MORNING_SLOT[night_slot]
    if night_slot == 6:
        # 23h–0h không có trên ca sáng — gộp vào slot 22h–23h
        return 13
    return None


def merge_night_into_morning(night: DailyWorkReport, morning: DailyWorkReport) -> dict:
    """Chuyển công đoạn + sản lượng từ ca tối sang ca sáng, rồi xóa ca tối."""
    stats = {'products': 0, 'entries': 0, 'comments': 0, 'deleted_night_id': night.pk}

    next_sort = (
        morning.production_products.order_by('-sort_order').values_list('sort_order', flat=True).first()
        or -1
    ) + 1

    for product in list(night.production_products.all()):
        old_first = product.first_slot_index
        new_first = _remap_slot(old_first)
        if new_first is None:
            new_first = old_first + 8 if old_first <= 5 else 13

        product.report = morning
        product.sort_order = next_sort
        product.first_slot_index = new_first
        product.save(update_fields=['report', 'sort_order', 'first_slot_index'])
        next_sort += 1
        stats['products'] += 1

        for entry in list(product.hourly_entries.all()):
            new_slot = _remap_slot(entry.slot_index)
            if new_slot is None:
                entry.delete()
                continue
            conflict = ProductionHourlyQuantity.objects.filter(
                product=product,
                slot_index=new_slot,
            ).exclude(pk=entry.pk).first()
            if conflict:
                conflict.quantity = (conflict.quantity or 0) + (entry.quantity or 0)
                conflict.damaged_quantity = (conflict.damaged_quantity or 0) + (
                    entry.damaged_quantity or 0
                )
                if entry.note and entry.note not in (conflict.note or ''):
                    conflict.note = ((conflict.note or '') + ' | ' + entry.note).strip(' |')[:500]
                conflict.save()
                entry.delete()
            else:
                entry.slot_index = new_slot
                entry.save(update_fields=['slot_index'])
            stats['entries'] += 1

    moved = ReportComment.objects.filter(daily_report=night).update(daily_report=morning)
    stats['comments'] = moved

    # Nếu ca tối đã nộp mà ca sáng còn nháp → giữ trạng thái đã nộp của ca tối
    if (
        night.status == DailyWorkReport.STATUS_SUBMITTED
        and morning.status != DailyWorkReport.STATUS_SUBMITTED
    ):
        morning.status = DailyWorkReport.STATUS_SUBMITTED
        morning.submitted_at = night.submitted_at or morning.submitted_at
        morning.save(update_fields=['status', 'submitted_at', 'updated_at'])

    night.delete()
    return stats


class Command(BaseCommand):
    help = 'Gộp ca tối bị nhầm (tăng ca ca sáng) vào báo cáo ca sáng.'

    def add_arguments(self, parser):
        parser.add_argument('--date', help='Một ngày YYYY-MM-DD')
        parser.add_argument('--from', dest='date_from', help='Từ ngày YYYY-MM-DD')
        parser.add_argument('--to', dest='date_to', help='Đến ngày YYYY-MM-DD')
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Thực sự ghi DB (mặc định chỉ liệt kê / dry-run)',
        )

    def handle(self, *args, **options):
        if options.get('date'):
            day = _parse_date(options['date'])
            date_from = date_to = day
        else:
            if not options.get('date_from') or not options.get('date_to'):
                # Mặc định: hôm qua
                yesterday = timezone.localdate() - timedelta(days=1)
                date_from = date_to = yesterday
                self.stdout.write(f'Không chỉ định ngày — dùng hôm qua: {yesterday.isoformat()}')
            else:
                date_from = _parse_date(options['date_from'])
                date_to = _parse_date(options['date_to'])
        if date_from > date_to:
            raise CommandError('--from phải <= --to')

        apply = bool(options['apply'])
        night_qs = (
            DailyWorkReport.objects.filter(
                report_profile=REPORT_PROFILE_PRODUCTION,
                shift=DailyWorkReport.SHIFT_NIGHT,
                report_date__gte=date_from,
                report_date__lte=date_to,
            )
            .select_related('employee', 'employee__profile')
            .prefetch_related(
                Prefetch(
                    'production_products',
                    queryset=ProductionShiftProduct.objects.prefetch_related('hourly_entries'),
                ),
            )
            .order_by('report_date', 'employee_id')
        )

        candidates = []
        skipped_real_night = 0
        for night in night_qs:
            morning = DailyWorkReport.objects.filter(
                employee_id=night.employee_id,
                report_date=night.report_date,
                report_profile=REPORT_PROFILE_PRODUCTION,
                shift=DailyWorkReport.SHIFT_MORNING,
            ).first()
            if not morning:
                continue
            if not is_misclassified_morning_overtime(night, morning):
                skipped_real_night += 1
                continue
            name = ''
            profile = getattr(night.employee, 'profile', None)
            if profile and profile.full_name:
                name = profile.full_name
            else:
                name = night.employee.username
            product_count = night.production_products.count()
            candidates.append((night, morning, name, product_count))

        self.stdout.write(
            f'Tìm thấy {len(candidates)} ca tối nghi tăng ca nhầm '
            f'({date_from} → {date_to}); bỏ qua {skipped_real_night} ca tối có dữ liệu qua đêm.'
        )
        if not candidates:
            return

        for night, morning, name, product_count in candidates:
            self.stdout.write(
                f'  - {night.report_date} | {name} ({night.employee.username}) | '
                f'night#{night.pk} → morning#{morning.pk} | {product_count} công đoạn'
            )

        if not apply:
            self.stdout.write(self.style.WARNING('Dry-run — thêm --apply để ghi DB.'))
            return

        merged = 0
        with transaction.atomic():
            for night, morning, name, _product_count in candidates:
                # re-fetch inside transaction
                night_obj = DailyWorkReport.objects.select_for_update().get(pk=night.pk)
                morning_obj = DailyWorkReport.objects.select_for_update().get(pk=morning.pk)
                stats = merge_night_into_morning(night_obj, morning_obj)
                merged += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ {name}: chuyển {stats["products"]} công đoạn, '
                        f'{stats["entries"]} dòng giờ; xóa night#{stats["deleted_night_id"]}'
                    )
                )

        self.stdout.write(self.style.SUCCESS(f'Đã gộp {merged} báo cáo ca tối nhầm vào ca sáng.'))
