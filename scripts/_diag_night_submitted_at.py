"""Đối chiếu submitted_at ca tối với giờ bắt đầu công đoạn đầu tiên và giờ bấm gửi thật."""
from django.db.models import Min
from django.utils import timezone

from reports.models import DailyWorkReport
from reports.report_lock import (
    production_approve_deadline,
    production_employee_edit_deadline,
)


def _fmt(dt):
    if not dt:
        return '—'
    return timezone.localtime(dt).strftime('%d/%m %H:%M')


reports = (
    DailyWorkReport.objects.filter(
        shift=DailyWorkReport.SHIFT_NIGHT,
        status=DailyWorkReport.STATUS_SUBMITTED,
    )
    .annotate(first_step_started_at=Min('production_products__started_at'))
    .select_related('employee', 'employee__profile')
    .order_by('-report_date', '-id')[:15]
)

mismatched = 0
print('pk | ngày BC | bắt đầu CĐ đầu | submitted_at | bấm gửi | tự động | hạn duyệt | hạn NV sửa | nhân viên')
for r in reports:
    anchor = r.first_step_started_at or r.shift_started_at
    if anchor and r.submitted_at != anchor:
        mismatched += 1
    profile = getattr(r.employee, 'profile', None)
    name = profile.full_name if profile and profile.full_name else r.employee.username
    print(
        f'{r.pk} | {r.report_date} | {_fmt(anchor)} | {_fmt(r.submitted_at)} | '
        f'{_fmt(r.submit_clicked_at)} | {r.auto_submitted} | '
        f'{_fmt(production_approve_deadline(r))} | {_fmt(production_employee_edit_deadline(r))} | {name}'
    )

print(f'\nSố báo cáo submitted_at chưa khớp giờ bắt đầu công đoạn đầu tiên: {mismatched}')

missing_anchor = DailyWorkReport.objects.filter(
    submitted_at__isnull=False,
    submit_clicked_at__isnull=True,
).count()
print(f'Số báo cáo đã gửi nhưng thiếu submit_clicked_at: {missing_anchor}')
