from django.contrib import admin
from .models import (
    DailyWorkReport,
    DailyWorkReportLine,
    WeeklyWorkReport,
    WeeklyWorkReportAttachment,
)


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


class WeeklyWorkReportAttachmentInline(admin.TabularInline):
    model = WeeklyWorkReportAttachment
    extra = 0
    readonly_fields = ('kind', 'file', 'original_name', 'created_at')
    fields = ('kind', 'file', 'original_name', 'created_at')
    can_delete = True


@admin.register(WeeklyWorkReport)
class WeeklyWorkReportAdmin(admin.ModelAdmin):
    list_display = (
        'employee',
        'week_start',
        'status',
        'attachment_count',
        'hod_reviewed',
        'submitted_at',
        'draft_saved_at',
    )
    list_filter = ('status', 'week_start', 'hod_reviewed')
    search_fields = ('employee__username', 'employee__profile__full_name', 'links', 'hod_note')
    date_hierarchy = 'week_start'
    readonly_fields = ('created_at', 'updated_at', 'submitted_at', 'draft_saved_at')
    inlines = [WeeklyWorkReportAttachmentInline]

    @admin.display(description='Đính kèm')
    def attachment_count(self, obj):
        return obj.attachments.count()


@admin.register(WeeklyWorkReportAttachment)
class WeeklyWorkReportAttachmentAdmin(admin.ModelAdmin):
    list_display = ('report', 'kind', 'display_name', 'created_at')
    list_filter = ('kind', 'created_at')
    search_fields = (
        'report__employee__username',
        'report__employee__profile__full_name',
        'original_name',
        'file',
    )
    readonly_fields = ('created_at',)
