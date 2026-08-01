"""Báo cáo SX bị quản lý sửa mà chưa duyệt — kiểm tra quyền duyệt của chính người sửa."""
from reports.models import DailyWorkReport
from reports.production_hourly import can_edit_production_norms
from reports.report_profile import REPORT_PROFILE_PRODUCTION

pending = (
    DailyWorkReport.objects.filter(
        report_profile=REPORT_PROFILE_PRODUCTION,
        status=DailyWorkReport.STATUS_SUBMITTED,
        hod_reviewed=False,
        production_products__updated_by__isnull=False,
    )
    .distinct()
    .select_related('employee')
    .order_by('-report_date')
)

print('pk | ngày | từ chối | người sửa | can_edit_production_norms | NV')
for report in pending:
    editors = {
        p.updated_by
        for p in report.production_products.select_related('updated_by')
        if p.updated_by_id
    }
    for editor in editors:
        print(
            f'{report.pk} | {report.report_date} | {report.hod_rejected} | '
            f'{editor.username} | {can_edit_production_norms(editor, report)} | '
            f'{report.employee.username}'
        )

print('\ntổng báo cáo treo:', pending.count())
print('trong đó bị từ chối:', pending.filter(hod_rejected=True).count())
