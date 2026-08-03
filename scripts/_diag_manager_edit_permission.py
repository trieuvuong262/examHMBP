"""Báo cáo SX bị quản lý sửa mà chưa duyệt — kiểm tra quyền duyệt của chính người sửa."""
from reports.models import DailyWorkReport
from reports.production_hourly import can_edit_production_norms
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.report_settings import auto_approve_manager_edited_reports

print('auto_approve_manager_edited_reports =', auto_approve_manager_edited_reports())

manager_edited = DailyWorkReport.objects.filter(
    report_profile=REPORT_PROFILE_PRODUCTION,
    production_products__updated_by__isnull=False,
).distinct()
print('tổng báo cáo có công đoạn do quản lý sửa:', manager_edited.count())
print('trong đó đã duyệt:', manager_edited.filter(hod_reviewed=True).count())

pending = (
    manager_edited.filter(
        status=DailyWorkReport.STATUS_SUBMITTED,
        hod_reviewed=False,
    )
    .select_related('employee')
    .order_by('-report_date')
)
print('còn treo chưa duyệt:', pending.count())

for report in pending:
    editors = {
        p.updated_by
        for p in report.production_products.select_related('updated_by')
        if p.updated_by_id
    }
    for editor in editors:
        print(
            f'{report.pk} | {report.report_date} | từ chối={report.hod_rejected} | '
            f'{editor.username} | duyệt được={can_edit_production_norms(editor, report)} | '
            f'{report.employee.username}'
        )
