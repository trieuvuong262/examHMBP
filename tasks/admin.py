from django.contrib import admin

from .models import (
    InternalProject,
    ProjectComment,
    WorkTask,
    WorkTaskAttachment,
    WorkTaskHandoff,
    WorkTaskLog,
    WorkTaskRecurrence,
)


@admin.register(InternalProject)
class InternalProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'status', 'due_date', 'updated_at')
    list_filter = ('status',)
    search_fields = ('title', 'owner__username')
    filter_horizontal = ('members',)
    raw_id_fields = ('owner',)


@admin.register(ProjectComment)
class ProjectCommentAdmin(admin.ModelAdmin):
    list_display = ('project', 'author', 'created_at')
    raw_id_fields = ('project', 'author')
    filter_horizontal = ('mentioned_users',)


@admin.register(WorkTaskHandoff)
class WorkTaskHandoffAdmin(admin.ModelAdmin):
    list_display = ('source_task', 'from_user', 'to_user', 'status', 'created_at')
    list_filter = ('status',)
    raw_id_fields = ('project', 'source_task', 'from_user', 'to_user', 'requested_by', 'reviewed_by', 'created_task')


@admin.register(WorkTaskAttachment)
class WorkTaskAttachmentAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'task', 'stage', 'uploaded_by', 'created_at')
    list_filter = ('stage',)
    raw_id_fields = ('task', 'uploaded_by')


@admin.register(WorkTaskRecurrence)
class WorkTaskRecurrenceAdmin(admin.ModelAdmin):
    list_display = ('title', 'assigner', 'assignee', 'frequency', 'interval', 'next_run_date', 'is_active')
    list_filter = ('is_active', 'frequency')
    search_fields = ('title', 'assigner__username', 'assignee__username')
    raw_id_fields = ('assigner', 'assignee')


@admin.register(WorkTask)
class WorkTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'assigner', 'assignee', 'status', 'priority', 'due_date', 'created_at')
    list_filter = ('status', 'priority', 'task_type')
    search_fields = ('title', 'assigner__username', 'assignee__username')
    raw_id_fields = ('assigner', 'assignee', 'reassigned_from', 'replaced_by', 'project', 'depends_on', 'recurrence')


@admin.register(WorkTaskLog)
class WorkTaskLogAdmin(admin.ModelAdmin):
    list_display = ('task', 'action', 'actor', 'created_at')
    list_filter = ('action',)
    raw_id_fields = ('task', 'actor')
