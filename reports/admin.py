from django.contrib import admin

from .models import (
    DailyWorkReport,
    DailyWorkReportAttachment,
    DailyWorkReportLine,
    ReportComment,
    ReportCommentAttachment,
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
        'submitted_at',
    )
    list_filter = ('status', 'report_profile', 'report_period', 'report_date', 'hod_reviewed', 'hod_rejected')
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
