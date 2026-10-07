from django.contrib import admin

from .models import (
    Candidate,
    CandidateEvent,
    CandidateFileKind,
    CandidateReview,
    CandidateSource,
    Interview,
    InterviewLocation,
    JobPosting,
)


@admin.register(InterviewLocation)
class InterviewLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'note', 'is_active', 'sort_order')


@admin.register(CandidateSource, CandidateFileKind)
class RecruitmentCodeOptionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'is_system', 'sort_order')


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ('title', 'target_department', 'position', 'quantity', 'deadline', 'status', 'created_at')
    list_filter = ('status', 'target_department', 'position')
    search_fields = ('title', 'department', 'description')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    raw_id_fields = ('service_request', 'created_by')


class CandidateEventInline(admin.TabularInline):
    model = CandidateEvent
    extra = 0
    can_delete = False
    readonly_fields = ('kind', 'from_status', 'to_status', 'message', 'actor', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'job_posting', 'phone', 'status', 'source', 'applied_at')
    list_filter = ('status', 'source', 'job_posting')
    search_fields = ('full_name', 'email', 'phone', 'job_posting__title')
    date_hierarchy = 'applied_at'
    ordering = ('-applied_at',)
    raw_id_fields = ('job_posting', 'referred_by', 'employee')
    # Trạng thái đi qua quy tắc nghiệp vụ trên portal — không sửa tay ở admin.
    readonly_fields = ('status', 'status_changed_at', 'employee')
    inlines = [CandidateEventInline]


@admin.register(CandidateReview)
class CandidateReviewAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'reviewer', 'decision', 'rating', 'updated_at')
    list_filter = ('decision',)
    raw_id_fields = ('candidate', 'reviewer')


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'interview_time', 'end_time', 'location', 'result')
    list_filter = ('result', 'interview_time')
    search_fields = ('candidate__full_name', 'location', 'result_notes')
    filter_horizontal = ('interviewers',)
    raw_id_fields = ('candidate',)
    date_hierarchy = 'interview_time'
