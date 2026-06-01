from django.contrib import admin

from .models import Feedback, FeedbackReply


class FeedbackReplyInline(admin.TabularInline):
    model = FeedbackReply
    extra = 0
    readonly_fields = ('author', 'body', 'is_staff_reply', 'created_at')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('title', 'submitter', 'category', 'status', 'assigned_to', 'created_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('title', 'body', 'submitter__username', 'submitter__first_name', 'submitter__last_name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [FeedbackReplyInline]


@admin.register(FeedbackReply)
class FeedbackReplyAdmin(admin.ModelAdmin):
    list_display = ('feedback', 'author', 'is_staff_reply', 'created_at')
    list_filter = ('is_staff_reply', 'created_at')
