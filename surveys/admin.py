from django.contrib import admin

from .models import Survey, SurveyAnswer, SurveyOption, SurveyQuestion, SurveyResponse, SurveyView


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'deadline', 'created_by', 'created_at')
    search_fields = ('title', 'question')
    readonly_fields = ('token', 'created_at', 'updated_at')


class SurveyOptionInline(admin.TabularInline):
    model = SurveyOption
    extra = 0


@admin.register(SurveyQuestion)
class SurveyQuestionAdmin(admin.ModelAdmin):
    list_display = ('survey', 'sort_order', 'q_type', 'is_required', 'content')
    list_filter = ('survey', 'q_type', 'is_required')
    inlines = (SurveyOptionInline,)


class SurveyAnswerInline(admin.TabularInline):
    model = SurveyAnswer
    extra = 0
    raw_id_fields = ('question', 'option')
    fields = ('question', 'option', 'text_value')


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('survey', 'full_name', 'employee_code', 'department_name', 'submitted_at')
    search_fields = ('full_name', 'employee_code', 'answer')
    list_filter = ('survey',)
    inlines = (SurveyAnswerInline,)


@admin.register(SurveyView)
class SurveyViewAdmin(admin.ModelAdmin):
    list_display = ('survey', 'full_name', 'employee_code', 'department_name', 'last_viewed_at')
    search_fields = ('full_name', 'employee_code')
    list_filter = ('survey',)
