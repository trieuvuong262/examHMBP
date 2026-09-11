"""Kiểm chứng sai lệch hiệu suất do làm tròn giờ công đoạn về 2 chữ số thập phân.

Ca sáng 07:30–08:20, SL 79, định mức 120/giờ → kỳ vọng 79,00% nhưng portal hiện 79,32%.
Chạy: python scripts/_diag_session_eff_rounding.py
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django  # noqa: E402

django.setup()

from datetime import date, datetime  # noqa: E402

from django.utils import timezone  # noqa: E402

from reports.models import DailyWorkReport, ProductionShiftProduct  # noqa: E402
from reports.production_hourly import session_effective_hours  # noqa: E402

TZ = timezone.get_default_timezone()
report_date = date(2026, 9, 11)


def aware(h, m):
    return timezone.make_aware(datetime.combine(report_date, datetime.min.time()), TZ).replace(
        hour=h, minute=m,
    )


report = DailyWorkReport(
    report_date=report_date,
    shift=DailyWorkReport.SHIFT_MORNING,
    report_profile='PRODUCTION',
)
product = ProductionShiftProduct(
    report=report,
    product_code='SC04',
    process_name='Kazai tay áo',
    norm_per_hour=Decimal('120'),
    started_at=aware(7, 30),
    ended_at=aware(8, 20),
    total_quantity=Decimal('79'),
    sort_order=0,
)

qty = Decimal('79')
norm = Decimal('120')
minutes = Decimal('50')

hours_code = session_effective_hours(product)
expected_code = norm * hours_code
pct_code = (qty / expected_code * 100).quantize(Decimal('0.01'))

hours_exact = minutes / Decimal('60')
expected_exact = norm * hours_exact
pct_exact = (qty / expected_exact * 100).quantize(Decimal('0.01'))

print('Bat dau / Ket thuc      : 07:30 - 08:20  (%s phut)' % minutes)
print('Dinh muc                : %s /gio' % norm)
print('San luong               : %s' % qty)
print()
print('--- session_effective_hours() hien tai')
print('  gio                   : %s  (= %s phut)' % (hours_code, hours_code * 60))
print('  SL ky vong            : %s' % expected_code)
print('  hieu suat             : %s%%' % pct_code)
print()
print('--- cong thuc dung (giu nguyen 50 phut)')
print('  gio                   : %s  (= %s phut)' % (
    hours_exact.quantize(Decimal('0.000001')), minutes,
))
print('  SL ky vong            : %s' % expected_exact.quantize(Decimal('0.01')))
print('  hieu suat             : %s%%' % pct_exact)
print()
print('=> lech: %s diem phan tram' % (pct_code - pct_exact))
