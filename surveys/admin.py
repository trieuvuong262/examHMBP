from django.contrib import admin

from .models import Survey, SurveyResponse


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'deadline', 'created_by', 'created_at')
    search_fields = ('title', 'question')
    readonly_fields = ('token', 'created_at', 'updated_at')


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('survey', 'full_name', 'employee_code', 'department_name', 'submitted_at')
    search_fields = ('full_name', 'employee_code', 'answer')
    list_filter = ('survey',)
