from django.contrib import admin

from .models import TienDoFeedback, TienDoItem


class TienDoFeedbackInline(admin.TabularInline):
    model = TienDoFeedback
    extra = 0
    fields = ('author', 'feedback', 'note', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(TienDoItem)
class TienDoItemAdmin(admin.ModelAdmin):
    list_display = ('feature', 'platform', 'created_by', 'completed_at', 'completed_by', 'updated_at')
    list_filter = ('platform', 'completed_at')
    search_fields = ('feature', 'description')
    inlines = [TienDoFeedbackInline]
