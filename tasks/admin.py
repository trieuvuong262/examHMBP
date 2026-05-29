from django.contrib import admin

from .models import WorkTask, WorkTaskLog


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
