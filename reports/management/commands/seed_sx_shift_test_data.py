"""Tạo dữ liệu test báo cáo SX ca sáng + ca tối cho NV phòng ban Sản xuất.

Sinh báo cáo (đã nộp) với:
  - Giờ bắt đầu / kết thúc ca ngẫu nhiên  → chia giờ theo khung thực tế
  - Định mức (norm_per_hour) ngẫu nhiên mỗi công đoạn
  - Mỗi ngày ít nhất 2 công đoạn
  - Mỗi NV mỗi ngày làm 1 ca (ngẫu nhiên sáng/tối) — giống thực tế

Chạy (local):
    python manage.py seed_sx_shift_test_data
    python manage.py seed_sx_shift_test_data --users 50 --from 2026-06-30 --to 2026-07-06

Chạy trên VPS (Docker):
    docker compose exec web python manage.py seed_sx_shift_test_data
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reports.models import (
    DailyWorkReport,
    ProductionHourlyQuantity,
    ProductionShiftProduct,
)
from reports.production_slots import (
    _slot_end_dt,
    _slot_start_dt,
    normalize_shift,
    slot_by_index,
    slots_overlapping_interval,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION

# (mã hàng, tên công đoạn) — ngành may thể thao
PRODUCTS = [
    ('AO-1001', 'May thân trước'),
    ('AO-1002', 'May thân sau'),
    ('AO-1003', 'Tra tay'),
    ('AO-1004', 'Vắt sổ'),
    ('QUAN-2001', 'Ráp đáy'),
    ('QUAN-2002', 'Tra lưng'),
    ('QUAN-2003', 'Lược lai'),
    ('IN-5001', 'In chuyển nhiệt'),
    ('THEU-6001', 'Thêu logo'),
    ('QC-3001', 'Kiểm hàng'),
    ('DG-4001', 'Đóng gói'),
]

NORMS = [Decimal(n) for n in (50, 60, 80, 100, 120, 150, 180, 200, 240)]

DEFAULT_FROM = date(2026, 6, 30)
DEFAULT_TO = date(2026, 7, 6)


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw.strip()[:10], '%Y-%m-%d').date()


def _split_contiguous(items: list, k: int) -> list[list]:
    """Chia list thành k đoạn liền kề, mỗi đoạn >= 1 phần tử."""
    n = len(items)
    k = max(1, min(k, n))
    # chọn k-1 điểm cắt trong (1..n-1)
    cuts = sorted(random.sample(range(1, n), k - 1)) if k > 1 else []
    chunks = []
    prev = 0
    for c in cuts:
        chunks.append(items[prev:c])
        prev = c
    chunks.append(items[prev:])
    return chunks


class Command(BaseCommand):
    help = 'Tạo báo cáo SX ca sáng + ca tối ngẫu nhiên để test số liệu tổng hợp.'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=50, help='Số NV SX (mặc định 50)')
        parser.add_argument('--from', dest='date_from', default=DEFAULT_FROM.isoformat())
        parser.add_argument('--to', dest='date_to', default=DEFAULT_TO.isoformat())
        parser.add_argument('--seed', type=int, default=None, help='Seed random (tùy chọn, để tái lập)')
        parser.add_argument(
            '--skip-sunday', action='store_true', default=True,
            help='Bỏ Chủ nhật (mặc định bật)',
        )
        parser.add_argument(
            '--include-sunday', dest='skip_sunday', action='store_false',
            help='Tạo cả Chủ nhật',
        )

    def handle(self, *args, **opts):
        if opts.get('seed') is not None:
            random.seed(opts['seed'])

        date_from = _parse_date(opts['date_from'])
        date_to = _parse_date(opts['date_to'])
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        num_users = max(1, opts['users'])
        skip_sunday = opts['skip_sunday']

        User = get_user_model()
        users = list(
            User.objects.filter(
                is_active=True,
                profile__is_employed=True,
                profile__department__report_profile=REPORT_PROFILE_PRODUCTION,
            )
            .select_related('profile', 'profile__department', 'profile__division')
            .order_by('id')[:num_users]
        )

        if not users:
            self.stderr.write(self.style.ERROR(
                'Không tìm thấy NV nào thuộc phòng ban Sản xuất (report_profile=PRODUCTION).'
            ))
            return

        self.stdout.write(f'NV Sản xuất sẽ tạo dữ liệu: {len(users)}')

        days = []
        d = date_from
        while d <= date_to:
            if not (skip_sunday and d.weekday() == 6):
                days.append(d)
            d += timedelta(days=1)
        self.stdout.write(f'Số ngày: {len(days)} ({date_from} → {date_to})')

        created_reports = 0
        created_products = 0
        with transaction.atomic():
            # Xoá báo cáo SX cũ của các NV này trong khoảng ngày (để chạy lại được)
            DailyWorkReport.objects.filter(
                employee__in=users,
                report_date__gte=date_from,
                report_date__lte=date_to,
                report_profile=REPORT_PROFILE_PRODUCTION,
            ).delete()

            for user in users:
                base_eff = random.randint(80, 108)
                for day in days:
                    # Mỗi NV mỗi ngày nộp cả 2 ca: sáng + tối
                    for shift in (DailyWorkReport.SHIFT_MORNING, DailyWorkReport.SHIFT_NIGHT):
                        n_prod = self._create_shift_report(user, day, shift, base_eff)
                        if n_prod:
                            created_reports += 1
                            created_products += n_prod

        self.stdout.write(self.style.SUCCESS(
            f'Đã tạo {created_reports} báo cáo SX (đã nộp), {created_products} công đoạn.'
        ))

    def _random_interval(self, day: date, shift: str):
        """(start_dt, end_dt) ngẫu nhiên trong khung ca — phút lẻ (vd 7h34, 21h03)."""
        shift = normalize_shift(shift)
        if shift == DailyWorkReport.SHIFT_MORNING:
            # bắt đầu 7h31–7h59 (phút lẻ, sau mốc 7h30)
            start = timezone.make_aware(datetime.combine(
                day, time(7, random.randint(31, 59))
            ))
            # kết thúc: đa số 16h–17h, đôi khi tăng ca tới 19h–22h — phút lẻ
            if random.random() < 0.72:
                end_hour = random.choice([16, 17])
            else:
                end_hour = random.choice([19, 20, 21, 22])
            end = timezone.make_aware(datetime.combine(
                day, time(end_hour, random.randint(1, 59))
            ))
        else:  # NIGHT — 17h hôm nay → 3h–5h hôm sau
            start = timezone.make_aware(datetime.combine(
                day, time(17, random.randint(1, 25))
            ))
            next_day = day + timedelta(days=1)
            end_hour = random.choice([3, 4, 5])
            # không vượt quá 5h00 (hết ca) → nếu kết thúc lúc 5h thì đúng 5h00
            minute = 0 if end_hour >= 5 else random.randint(1, 59)
            end = timezone.make_aware(datetime.combine(next_day, time(end_hour, minute)))
        return start, end

    def _create_shift_report(self, user, day: date, shift: str, base_eff: int) -> int:
        shift = normalize_shift(shift)
        start_dt, end_dt = self._random_interval(day, shift)
        slots = slots_overlapping_interval(day, shift, start_dt, end_dt)
        if len(slots) < 2:
            return 0

        now = timezone.now()
        report = DailyWorkReport.objects.create(
            employee=user,
            report_date=day,
            shift=shift,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period='day',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=now,
            draft_saved_at=now,
            shift_started_at=start_dt,
        )

        # mỗi ngày >= 2 công đoạn
        max_stages = min(3, len(slots))
        n_stages = random.randint(2, max_stages)
        chunks = _split_contiguous(slots, n_stages)
        picks = random.sample(PRODUCTS, len(chunks))

        n_chunks = len(chunks)
        for sort_order, (chunk, (code, process)) in enumerate(zip(chunks, picks)):
            norm = random.choice(NORMS)
            eff = max(50, min(130, base_eff + random.randint(-12, 12)))
            first_slot_index = chunk[0][0]
            last_slot_index = chunk[-1][0]
            is_first = sort_order == 0
            is_last = sort_order == n_chunks - 1

            total_qty = Decimal('0')
            entries = []
            for slot_index, hours in chunk:
                hours = Decimal(hours)
                qty = (Decimal(eff) / Decimal('100') * norm * hours).quantize(
                    Decimal('1'), rounding=ROUND_HALF_UP
                )
                if qty <= 0:
                    qty = Decimal('1')
                total_qty += qty
                entries.append((slot_index, qty, hours))

            first_slot = slot_by_index(first_slot_index, shift)
            last_slot = slot_by_index(last_slot_index, shift)
            # Công đoạn đầu dùng đúng giờ bắt đầu lẻ; công đoạn cuối dùng giờ kết thúc lẻ
            started_at = start_dt if is_first else (
                _slot_start_dt(day, first_slot) if first_slot else start_dt
            )
            ended_at = end_dt if is_last else (
                _slot_end_dt(day, last_slot) if last_slot else end_dt
            )
            product = ProductionShiftProduct.objects.create(
                report=report,
                product_code=code,
                process_name=process,
                norm_per_hour=norm,
                status=ProductionShiftProduct.STATUS_DONE,
                sort_order=sort_order,
                first_slot_index=first_slot_index,
                started_at=started_at,
                ended_at=ended_at,
                total_quantity=total_qty,
                total_damaged_quantity=0,
                completion_note='',
                submitted_locked=True,
            )
            ProductionHourlyQuantity.objects.bulk_create([
                ProductionHourlyQuantity(
                    product=product,
                    slot_index=slot_index,
                    quantity=qty,
                    damaged_quantity=0,
                    note='',
                    partial_hours=hours,
                    zero_reason='',
                )
                for slot_index, qty, hours in entries
            ])

        return len(chunks)
