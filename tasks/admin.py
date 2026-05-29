from django.contrib import admin

from .models import WorkTask, WorkTaskAttachment, WorkTaskLog


@admin.register(WorkTaskAttachment)
class WorkTaskAttachmentAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'task', 'stage', 'uploaded_by', 'created_at')
    list_filter = ('stage',)
    raw_id_fields = ('task', 'uploaded_by')


@admin.register(WorkTask)
class WorkTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'assigner', 'assignee', 'status', 'priority', 'due_date', 'created_at')
    list_filter = ('status', 'priority', 'task_type')
    search_fields = ('title', 'assigner__username', 'assignee__username')
    raw_id_fields = ('assigner', 'assignee', 'reassigned_from', 'replaced_by')


@admin.register(WorkTaskLog)
class WorkTaskLogAdmin(admin.ModelAdmin):
    list_display = ('task', 'action', 'actor', 'created_at')
    list_filter = ('action',)
    raw_id_fields = ('task', 'actor')
