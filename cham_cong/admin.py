from django.contrib import admin

from cham_cong.permissions import attendance_demo_user
from cham_cong.models import (
    AttendanceAdjustment,
    AttendanceDay,
    AttendanceLog,
    AttendancePolicy,
    AttendanceSupplement,
    Holiday,
    Shift,
    ShiftAssignment,
    TimesheetPeriod,
    LeaveRequest,
    PayAdjustment,
    PayrollPeriod,
    PayrollSlip,
    SalaryProfile,
    WorkSite,
    WorkSiteIp,
)


class WorkSiteIpInline(admin.TabularInline):
    model = WorkSiteIp
    extra = 1


class AttendanceDemoAdmin(admin.ModelAdmin):
    """Admin-panel cũng chỉ vuong-admin xem dữ liệu chấm công."""

    def has_module_permission(self, request):
        return attendance_demo_user(request.user)

    def has_view_permission(self, request, obj=None):
        return attendance_demo_user(request.user)

    def has_add_permission(self, request):
        return attendance_demo_user(request.user)

    def has_change_permission(self, request, obj=None):
        return attendance_demo_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return attendance_demo_user(request.user)


@admin.register(WorkSite)
class WorkSiteAdmin(AttendanceDemoAdmin):
    list_display = ('name', 'latitude', 'longitude', 'radius_m', 'is_active')
    inlines = [WorkSiteIpInline]


admin.site.register(AttendancePolicy, AttendanceDemoAdmin)
admin.site.register(Shift, AttendanceDemoAdmin)
admin.site.register(ShiftAssignment, AttendanceDemoAdmin)
admin.site.register(Holiday, AttendanceDemoAdmin)
admin.site.register(AttendanceDay, AttendanceDemoAdmin)
admin.site.register(AttendanceSupplement, AttendanceDemoAdmin)
admin.site.register(AttendanceAdjustment, AttendanceDemoAdmin)
admin.site.register(TimesheetPeriod, AttendanceDemoAdmin)
admin.site.register(LeaveRequest, AttendanceDemoAdmin)
admin.site.register(SalaryProfile, AttendanceDemoAdmin)
admin.site.register(PayrollPeriod, AttendanceDemoAdmin)
admin.site.register(PayrollSlip, AttendanceDemoAdmin)
admin.site.register(PayAdjustment, AttendanceDemoAdmin)
admin.site.register(AttendanceLog, AttendanceDemoAdmin)
admin.site.register(WorkSiteIp, AttendanceDemoAdmin)
