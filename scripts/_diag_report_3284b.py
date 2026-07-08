from reports.models import DailyWorkReport
from reports.report_lock import production_manager_edit_deadline, production_manager_may_edit, is_production_manager_edit_expired
from django.utils import timezone

r = DailyWorkReport.objects.get(pk=3284)
print("submitted_at", r.submitted_at)
print("updated_at", r.updated_at)
print("hod_reviewed_at", r.hod_reviewed_at)
print("deadline", production_manager_edit_deadline(r))
print("expired", is_production_manager_edit_expired(r))
print("may_edit", production_manager_may_edit(r))
print("now", timezone.now())
