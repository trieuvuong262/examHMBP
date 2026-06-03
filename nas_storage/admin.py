from django.contrib import admin

from nas_storage.models import NasShareLink, NasUserFolderAccess


@admin.register(NasShareLink)
class NasShareLinkAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'created_by', 'rel_path', 'is_dir', 'expires_at', 'is_active')
    list_filter = ('is_active', 'is_dir')
    search_fields = ('item_name', 'rel_path', 'created_by__username')
    readonly_fields = ('token', 'created_at')


@admin.register(NasUserFolderAccess)
class NasUserFolderAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'rel_path', 'is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'label', 'rel_path')
    ordering = ('user__username', 'sort_order')
