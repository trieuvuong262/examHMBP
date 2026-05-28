from django.contrib import admin
from .models import DailyWorkReport, DailyWorkReportLine


class DailyWorkReportLineInline(admin.TabularInline):
    model = DailyWorkReportLine
    extra = 0


@admin.register(DailyWorkReport)
class DailyWorkReportAdmin(admin.ModelAdmin):
    list_display = ('employee', 'report_date', 'shift', 'status', 'hod_reviewed', 'submitted_at')
    list_filter = ('status', 'shift', 'report_date', 'hod_reviewed')
    search_fields = ('employee__username', 'employee__profile__full_name')
    date_hierarchy = 'report_date'
    inlines = [DailyWorkReportLineInline]
