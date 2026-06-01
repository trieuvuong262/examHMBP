from django.contrib import admin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('title', 'submitter_display', 'is_anonymous', 'created_at')
    list_filter = ('is_anonymous', 'created_at')
    search_fields = ('title', 'body', 'submitter__username', 'submitter__first_name', 'submitter__last_name')
    readonly_fields = ('created_at',)

    @admin.display(description='Người gửi')
    def submitter_display(self, obj):
        return obj.submitter_display()
