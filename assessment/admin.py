from django.contrib import admin

from .models import ExamQuestion


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'sort_order', 'question')
    list_filter = ('exam',)
    search_fields = ('exam__title', 'question__content')
    ordering = ('exam', 'sort_order', 'id')
