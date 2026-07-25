from django.contrib import admin

from .models import (
    DailyWorkReport,
    DailyWorkReportAttachment,
    DailyWorkReportLine,
    ProductionReportReminderLog,
    ReportComment,
    ReportCommentAttachment,
    ReportsGeneralSettings,
    WeeklyWorkReport,
    WeeklyWorkReportAttachment,
)


class DailyWorkReportLineInline(admin.TabularInline):
    model = DailyWorkReportLine
    extra = 0


class DailyWorkReportAttachmentInline(admin.TabularInline):
    model = DailyWorkReportAttachment
    extra = 0
    readonly_fields = ('kind', 'source_tab', 'file', 'original_name', 'created_at')
    fields = ('source_tab', 'kind', 'file', 'original_name', 'created_at')
    can_delete = True


@admin.register(DailyWorkReport)
class DailyWorkReportAdmin(admin.ModelAdmin):
    list_display = (
        'employee',
        'report_date',
        'report_profile',
        'report_period',
        'status',
        'attachment_count',
        'hod_reviewed',
        'hod_rejected',
        'auto_submitted',
        'submitted_at',
    )
    list_filter = (
        'status',
        'report_profile',
        'report_period',
        'report_date',
        'hod_reviewed',
        'hod_rejected',
        'auto_submitted',
    )
    search_fields = ('employee__username', 'employee__profile__full_name', 'title')
    date_hierarchy = 'report_date'
    readonly_fields = ('created_at', 'updated_at', 'submitted_at', 'draft_saved_at')
    inlines = [DailyWorkReportLineInline, DailyWorkReportAttachmentInline]

    @admin.display(description='Đính kèm')
    def attachment_count(self, obj):
        return obj.attachments.count()


@admin.register(DailyWorkReportAttachment)
class DailyWorkReportAttachmentAdmin(admin.ModelAdmin):
    list_display = ('report', 'source_tab', 'kind', 'display_name', 'created_at')
    list_filter = ('kind', 'source_tab', 'created_at', 'report__report_profile', 'report__report_period')
    search_fields = (
        'report__employee__username',
        'report__employee__profile__full_name',
        'original_name',
        'file',
    )
    readonly_fields = ('created_at',)

    @admin.display(description='Tên file')
    def display_name(self, obj):
        return obj.display_name


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


class ReportCommentAttachmentInline(admin.TabularInline):
    model = ReportCommentAttachment
    extra = 0
    readonly_fields = ('kind', 'file', 'original_name', 'created_at')
    fields = ('kind', 'file', 'original_name', 'created_at')
    can_delete = True


@admin.register(ReportComment)
class ReportCommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'daily_report', 'weekly_report', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = (
        'author__username',
        'author__profile__full_name',
        'body',
        'daily_report__employee__username',
        'weekly_report__employee__username',
    )
    readonly_fields = ('created_at',)
    inlines = [ReportCommentAttachmentInline]


@admin.register(ProductionReportReminderLog)
class ProductionReportReminderLogAdmin(admin.ModelAdmin):
    list_display = ('employee', 'report_date', 'shift', 'wave', 'sent_at')
    list_filter = ('shift', 'wave', 'report_date')
    search_fields = ('employee__username', 'employee__profile__full_name')
    readonly_fields = ('sent_at',)


@admin.register(ReportsGeneralSettings)
class ReportsGeneralSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'auto_submit_time',
        'default_declared_work_hours',
        'work_hours_min',
        'work_hours_max',
        'auto_approve_proxy_reports',
        'approve_deadline_hours',
        'auto_reject_deadline_hours',
        'employee_edit_deadline_hours',
        'unapprove_deadline_days',
        'updated_at',
    )
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not ReportsGeneralSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
