from django.contrib import admin

from utilities.models import ScheduleReminder, ScheduleReminderPushLog


@admin.register(ScheduleReminder)
class ScheduleReminderAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'repeat_mode', 'remind_time', 'once_date', 'is_active')
    list_filter = ('is_active', 'repeat_mode')
    search_fields = ('title', 'body', 'user__username')
    raw_id_fields = ('user',)
    ordering = ('-created_at',)


@admin.register(ScheduleReminderPushLog)
class ScheduleReminderPushLogAdmin(admin.ModelAdmin):
    list_display = ('reminder', 'fire_date', 'sent_at')
    list_filter = ('fire_date',)
    raw_id_fields = ('reminder',)
    ordering = ('-sent_at',)
