"""
Nhập dữ liệu báo cáo SX test — ngày hôm nay (giờ VPS), thời gian bắt đầu/kết thúc ngẫu nhiên trong khung ca.

Usage:
    python scripts/seed_production_test_report.py vananh
    python scripts/seed_production_test_report.py vananh --clear
    docker compose exec -T web python scripts/seed_production_test_report.py vananh --clear
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from reports.models import DailyWorkReport, ProductionShiftProduct
from reports.period_utils import PERIOD_DAY
from reports.production_hourly import complete_work_session
from reports.production_shift_policy import production_reports_for_day
from reports.production_slots import _slot_end_dt, _slot_start_dt, slots_for_shift
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()

MORNING_PRODUCTS = (
    ('TEST-AM-01', 'May thân', Decimal('85')),
    ('TEST-AM-02', 'Đóng gói', Decimal('120')),
    ('TEST-AM-03', 'Kiểm QC', Decimal('95')),
)

NIGHT_PRODUCTS = (
    ('TEST-PM-01', 'May tay áo', Decimal('70')),
    ('TEST-PM-02', 'Ủi hoàn thiện', Decimal('60')),
)


def _can_seed_night_same_day(user, report_date) -> bool:
    from reports.production_shift_policy import can_start_production_shift

    ok, _ = can_start_production_shift(user, report_date, DailyWorkReport.SHIFT_NIGHT)
    return ok

def _rand_dt_between(start: datetime, end: datetime) -> datetime:
    if end <= start:
        return start
    delta = int((end - start).total_seconds())
    offset = random.randint(0, max(delta, 1))
    return start + timedelta(seconds=offset)


def _random_session_times(report_date, shift: str) -> tuple[datetime, datetime, int]:
    slots = slots_for_shift(shift)
    if len(slots) < 2:
        raise ValueError(f'Ca {shift} không đủ khung giờ.')

    start_idx = random.randint(0, len(slots) - 2)
    end_idx = random.randint(start_idx + 1, len(slots) - 1)

    start_slot = slots[start_idx]
    end_slot = slots[end_idx]
    slot_start = _slot_start_dt(report_date, start_slot)
    slot_end = _slot_end_dt(report_date, end_slot)

    started_at = _rand_dt_between(slot_start, _slot_end_dt(report_date, start_slot) - timedelta(minutes=5))
    ended_at = _rand_dt_between(_slot_start_dt(report_date, end_slot), slot_end - timedelta(minutes=1))
    if ended_at <= started_at:
        ended_at = started_at + timedelta(minutes=random.randint(15, 90))

    return started_at, ended_at, start_idx


@transaction.atomic
def seed_shift(user, report_date, shift: str, products: tuple, *, clear: bool) -> int:
    existing = production_reports_for_day(user, report_date).filter(shift=shift).first()
    if existing and clear:
        existing.delete()
        existing = None

    if existing:
        report = existing
        report.production_products.all().delete()
        report.shift_started_at = None
        report.status = DailyWorkReport.STATUS_DRAFT
        report.submitted_at = None
        report.hod_reviewed = False
        report.save()
    else:
        report = DailyWorkReport.objects.create(
            employee=user,
            report_date=report_date,
            shift=shift,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period=PERIOD_DAY,
            status=DailyWorkReport.STATUS_DRAFT,
        )

    earliest_start = None
    for sort_order, (code, process, norm) in enumerate(products):
        started_at, ended_at, first_slot = _random_session_times(report_date, shift)
        if earliest_start is None or started_at < earliest_start:
            earliest_start = started_at

        product = ProductionShiftProduct.objects.create(
            report=report,
            product_code='',
            process_name='',
            sort_order=sort_order,
            first_slot_index=first_slot,
            status=ProductionShiftProduct.STATUS_ACTIVE,
            started_at=started_at,
            ended_at=ended_at,
        )

        qty = Decimal(str(random.randint(int(norm * 2), int(norm * 5))))
        damaged = random.randint(0, 2) if qty > 0 else 0
        complete_work_session(
            report,
            product_code=code,
            process_name=process,
            norm_per_hour=norm,
            total_quantity=qty,
            damaged_quantity=damaged,
            note=f'Test seed {report_date} — phiên {sort_order + 1}',
        )
        product.refresh_from_db()

    report.shift_started_at = earliest_start
    report.draft_saved_at = timezone.now()
    report.save(update_fields=['shift_started_at', 'draft_saved_at', 'status', 'submitted_at', 'hod_reviewed'])

    return report.pk


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print('Usage: seed_production_test_report.py <username> [--clear]')
        return 1

    username = argv[0]
    clear = '--clear' in argv

    user = User.objects.filter(username__iexact=username).first()
    if not user:
        print(f'ERROR: user {username!r} not found')
        return 1

    report_date = timezone.localdate()
    random.seed(f'{username}-{report_date.isoformat()}')

    morning_pk = seed_shift(user, report_date, DailyWorkReport.SHIFT_MORNING, MORNING_PRODUCTS, clear=clear)

    night_pk = None
    if _can_seed_night_same_day(user, report_date):
        night_pk = seed_shift(user, report_date, DailyWorkReport.SHIFT_NIGHT, NIGHT_PRODUCTS, clear=clear)
    else:
        prev = report_date - timedelta(days=1)
        if _can_seed_night_same_day(user, prev):
            night_pk = seed_shift(user, prev, DailyWorkReport.SHIFT_NIGHT, NIGHT_PRODUCTS, clear=clear)

    print(f'OK user={user.username} id={user.pk} date={report_date}')
    print(f'  ca sáng report_id={morning_pk} products={len(MORNING_PRODUCTS)}')
    if night_pk:
        print(f'  ca tối  report_id={night_pk} products={len(NIGHT_PRODUCTS)}')
    else:
        print('  ca tối  skipped (đã có ca sáng cùng ngày hoặc không mở được)')
    print(f'  URL ca sáng: /reports/sx/{morning_pk}/')
    if night_pk:
        print(f'  URL ca tối:  /reports/sx/{night_pk}/')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
