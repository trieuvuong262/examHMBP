from django.contrib import admin

from .models import TienDoItem


@admin.register(TienDoItem)
class TienDoItemAdmin(admin.ModelAdmin):
    list_display = ('feature', 'platform', 'is_tested', 'created_by', 'updated_at')
    list_filter = ('platform', 'is_tested')
    search_fields = ('feature', 'description')
