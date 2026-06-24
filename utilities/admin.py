from django.contrib import admin

from utilities.models import ScheduleReminder


@admin.register(ScheduleReminder)
class ScheduleReminderAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'remind_at', 'push_sent_at', 'is_active')
    list_filter = ('is_active', 'push_sent_at')
    search_fields = ('title', 'body', 'user__username')
    raw_id_fields = ('user',)
    ordering = ('-remind_at',)
