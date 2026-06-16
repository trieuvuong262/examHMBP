from django.contrib import admin

from .models import Candidate, Interview, JobPosting


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ('title', 'department', 'position', 'quantity', 'deadline', 'is_active', 'created_at')
    list_filter = ('is_active', 'department', 'position')
    search_fields = ('title', 'department', 'description')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'job_posting', 'email', 'phone', 'status', 'applied_at')
    list_filter = ('status', 'job_posting')
    search_fields = ('full_name', 'email', 'phone', 'job_posting__title')
    date_hierarchy = 'applied_at'
    ordering = ('-applied_at',)
    raw_id_fields = ('job_posting',)


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'interview_time', 'location', 'passed')
    list_filter = ('passed', 'interview_time')
    search_fields = ('candidate__full_name', 'location', 'result_notes')
    filter_horizontal = ('interviewers',)
    raw_id_fields = ('candidate',)
    date_hierarchy = 'interview_time'
