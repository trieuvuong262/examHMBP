from django.contrib import admin
from .models import MetabaseReport

@admin.register(MetabaseReport)
class MetabaseReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'report_type', 'is_active', 'created_at')
    list_filter = ('report_type', 'is_active')
    search_fields = ('title',)