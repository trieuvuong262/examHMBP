"""Kiểm tra vì sao báo cáo nhập hộ / quản lý sửa không tự chuyển sang Đã duyệt."""
from django.utils import timezone

from reports.models import DailyWorkReport, ReportsGeneralSettings
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.report_settings import auto_approve_proxy_reports


def _fmt(dt):
    return timezone.localtime(dt).strftime('%d/%m %H:%M') if dt else '—'


settings_row = ReportsGeneralSettings.objects.first()
print('ReportsGeneralSettings row:', settings_row.pk if settings_row else None)
print('auto_approve_proxy_reports (helper):', auto_approve_proxy_reports())
if settings_row:
    print('auto_approve_proxy_reports (DB):', settings_row.auto_approve_proxy_reports)

qs = DailyWorkReport.objects.filter(
    report_profile=REPORT_PROFILE_PRODUCTION,
    status=DailyWorkReport.STATUS_SUBMITTED,
).select_related('proxy_entered_by', 'employee')

print('\n-- Báo cáo SX đã gửi, 14 ngày gần nhất --')
recent = qs.filter(report_date__gte=timezone.localdate() - timezone.timedelta(days=14))
print('tổng:', recent.count())
print('có proxy_entered_by:', recent.filter(proxy_entered_by__isnull=False).count())
print('proxy + chưa duyệt:', recent.filter(proxy_entered_by__isnull=False, hod_reviewed=False).count())
print('không proxy + chưa duyệt:', recent.filter(proxy_entered_by__isnull=True, hod_reviewed=False).count())

print('\npk | ngày | ca | proxy_entered_by | duyệt | từ chối | NV')
for r in recent.order_by('-report_date', '-id')[:20]:
    proxy = r.proxy_entered_by.username if r.proxy_entered_by else '—'
    print(
        f'{r.pk} | {r.report_date} | {r.shift} | {proxy} | {r.hod_reviewed} | '
        f'{r.hod_rejected} | {r.employee.username}'
    )

print('\n-- Công đoạn có updated_by (quản lý đã sửa) nhưng báo cáo chưa duyệt --')
edited = recent.filter(
    hod_reviewed=False,
    production_products__updated_by__isnull=False,
).distinct()
print('số báo cáo:', edited.count())
for r in edited.order_by('-report_date', '-id')[:15]:
    editors = sorted({
        p.updated_by.username
        for p in r.production_products.all()
        if p.updated_by_id
    })
    proxy = r.proxy_entered_by.username if r.proxy_entered_by else '—'
    print(
        f'{r.pk} | {r.report_date} | {r.shift} | proxy={proxy} | '
        f'sửa bởi={",".join(editors)} | duyệt={r.hod_reviewed} | NV={r.employee.username}'
    )
