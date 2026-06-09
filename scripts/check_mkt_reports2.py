"""Kiểm tra workflow báo cáo MKT — quyền xem/duyệt."""
from django.contrib.auth.models import User

from hrm.models import Department
from hrm.permissions import can_review_user_report, can_view_user_report, can_view_team_reports
from reports.models import DailyWorkReport
from service_requests.workflow import find_department_head_manager

dept = Department.objects.get(name__icontains='MARKETING')
ductn = User.objects.get(username='Ductn')
sample = User.objects.get(username='Dinhgiang')

print('=== WORKFLOW ===')
mgr = find_department_head_manager(sample)
print(f'find_department_head_manager(Dinhgiang) = {mgr.username if mgr else None}')

print('\n=== QUYỀN Ductn (GD + kiêm TP MKT) ===')
print(f'can_view_team_reports: {can_view_team_reports(ductn)}')

report = DailyWorkReport.objects.filter(employee=sample).first()
if report:
    print(f'Báo cáo Dinhgiang id={report.pk} status={report.status}')
    print(f'can_view_user_report(Ductn): {can_view_user_report(ductn, report)}')
    print(f'can_review_user_report(Ductn): {can_review_user_report(ductn, report)}')
else:
    print('Dinhgiang chưa có báo cáo trong DB')

# NV không thuộc 6 cấp dưới thủ công
other = User.objects.get(username='huuan')
print(f'\n=== NV ngoài 6 cấp dưới thủ công: {other.username} ===')
print(f'find_department_head_manager = {find_department_head_manager(other).username}')
r2 = DailyWorkReport.objects.filter(employee=other).first()
if r2:
    print(f'can_review Ductn: {can_review_user_report(ductn, r2)}')
else:
    print('Chưa có báo cáo — giả lập quyền khi có báo cáo:')
    fake = DailyWorkReport(employee=other, report_date='2026-06-09')
    print(f'can_view_user_report(Ductn, fake): {can_view_user_report(ductn, fake)}')
