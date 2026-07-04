"""Tạo dữ liệu test hiệu suất SX cho cấp dưới của vuonglnt (trừ HUỲNH THỊ CẨM TÚ).

Chạy:  python scripts/seed_summary_test_data.py
"""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from hrm.permissions import get_team_report_members
from reports.models import (
    DailyWorkReport,
    ProductionHourlyQuantity,
    ProductionShiftProduct,
)
from reports.report_profile import (
    REPORT_PROFILE_PRODUCTION,
    filter_team_members_for_report_profile,
)

DATE_FROM = date(2026, 7, 4)
DATE_TO = date(2026, 7, 17)
EXCLUDE_NAME = 'HUỲNH THỊ CẨM TÚ'

PRODUCTS = [
    ('SP-A01', 'May thân trước'),
    ('SP-B02', 'Ráp đáy'),
    ('SP-C03', 'Kiểm hàng'),
    ('SP-D04', 'Đóng gói'),
]

User = get_user_model()
leader = User.objects.filter(username__iexact='vuonglnt').first()
if not leader:
    print('KHONG TIM THAY quan ly vuonglnt')
    sys.exit(1)

team = filter_team_members_for_report_profile(
    get_team_report_members(leader).select_related('profile'),
    REPORT_PROFILE_PRODUCTION,
)


def _norm(name: str) -> str:
    return ' '.join((name or '').split()).strip().upper()


targets = []
for member in team:
    profile = getattr(member, 'profile', None)
    full_name = (profile.full_name if profile and profile.full_name else member.username)
    if _norm(full_name) == _norm(EXCLUDE_NAME):
        print(f'BO QUA: {full_name}')
        continue
    targets.append((member, full_name))

print(f'So NV se tao du lieu: {len(targets)}')


def _dt(d: date, hh: int, mm: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(d, time(hh, mm)))


created_reports = 0
for member, full_name in targets:
    rnd = random.Random(f'{member.id}-seed')
    base_eff = rnd.randint(78, 108)  # mức hiệu suất nền của NV

    day = DATE_FROM
    while day <= DATE_TO:
        if day.weekday() == 6:  # Chủ nhật nghỉ
            day += timedelta(days=1)
            continue

        # Xoá báo cáo SX cũ cùng ngày (nếu có) để chạy lại được nhiều lần
        DailyWorkReport.objects.filter(
            employee=member,
            report_date=day,
            report_profile=REPORT_PROFILE_PRODUCTION,
            shift=DailyWorkReport.SHIFT_MORNING,
        ).delete()

        now = timezone.now()
        report = DailyWorkReport.objects.create(
            employee=member,
            report_date=day,
            shift=DailyWorkReport.SHIFT_MORNING,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period='day',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=now,
            draft_saved_at=now,
            shift_started_at=_dt(day, 7, 30),
        )

        # 2–3 công đoạn, mỗi cái có hiệu suất & thời gian khác nhau
        num = rnd.choice([2, 3])
        picks = rnd.sample(PRODUCTS, num)
        hours_pool = [Decimal('1.8'), Decimal('2.0'), Decimal('2.5'), Decimal('3.0'), Decimal('1.5')]
        for i, (code, process) in enumerate(picks):
            hours = rnd.choice(hours_pool)
            eff = max(45, base_eff + rnd.randint(-15, 15))  # % mục tiêu
            norm = Decimal('100')
            qty = (Decimal(eff) / Decimal('100') * norm * hours).quantize(Decimal('1'))
            slot = i  # khung giờ riêng cho từng công đoạn

            product = ProductionShiftProduct.objects.create(
                report=report,
                product_code=code,
                process_name=process,
                norm_per_hour=norm,
                status=ProductionShiftProduct.STATUS_DONE,
                sort_order=i,
                first_slot_index=slot,
                started_at=_dt(day, 7 + i * 2, 30),
                ended_at=_dt(day, 9 + i * 2, 30),
                total_quantity=qty,
                total_damaged_quantity=0,
                completion_note='',
            )
            ProductionHourlyQuantity.objects.create(
                product=product,
                slot_index=slot,
                quantity=qty,
                damaged_quantity=0,
                note='',
                partial_hours=hours,
                zero_reason='',
            )
        created_reports += 1
        day += timedelta(days=1)

print(f'DA TAO {created_reports} bao cao SX (SUBMITTED) tu {DATE_FROM} den {DATE_TO}.')
