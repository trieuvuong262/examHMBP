"""Mở lại báo cáo SX ngày 19/09/2026 bị tự «Không duyệt» khi chưa hết giờ làm việc.

Chạy trên VPS SAU khi deploy:

  docker compose exec -T web python manage.py shell < scripts/_reopen_sx_rejected_working_hours.py
"""

from datetime import date

from django.utils import timezone

from reports.report_lock import reopen_auto_rejected_within_working_hours

REPORT_DAY = date(2026, 9, 19)
print('now', timezone.localtime())
ids = reopen_auto_rejected_within_working_hours(date_from=REPORT_DAY, date_to=REPORT_DAY)
print('reopened', len(ids))
for pk in ids:
    print(' ', pk)
if not ids:
    print('nothing to reopen')
