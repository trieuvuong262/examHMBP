from django.contrib import admin

from .models import Announcement, AnnouncementRead


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'content_type', 'is_active', 'is_pinned', 'created_by', 'created_at')
    list_filter = ('content_type', 'is_active', 'is_pinned')
    search_fields = ('title', 'summary')


@admin.register(AnnouncementRead)
class AnnouncementReadAdmin(admin.ModelAdmin):
    list_display = ('announcement', 'user', 'read_at')
    list_filter = ('read_at',)
