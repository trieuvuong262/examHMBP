from django.contrib import admin

from nas_storage.models import (
    NasAccessGroup,
    NasFolderPermission,
    NasShareFolder,
    NasShareLink,
    NasUserFolderAccess,
    NasUserFolderAcl,
)


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


@admin.register(NasAccessGroup)
class NasAccessGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'nas_principal', 'portal_browse_all', 'is_active', 'sort_order')
    search_fields = ('name', 'nas_principal')
    filter_horizontal = ('portal_members', 'portal_excluded_members')


@admin.register(NasShareFolder)
class NasShareFolderAdmin(admin.ModelAdmin):
    list_display = ('share_name', 'display_name', 'is_active', 'sort_order')
    search_fields = ('share_name', 'display_name')


@admin.register(NasFolderPermission)
class NasFolderPermissionAdmin(admin.ModelAdmin):
    list_display = ('folder', 'group', 'permission_type', 'last_applied_at')
    list_filter = ('permission_type',)
    search_fields = ('folder__share_name', 'group__name')


@admin.register(NasUserFolderAcl)
class NasUserFolderAclAdmin(admin.ModelAdmin):
    list_display = ('user', 'folder', 'sub_path', 'access_level', 'is_active', 'last_applied_at')
    list_filter = ('is_active', 'access_level')
    search_fields = ('user__username', 'sub_path', 'folder__share_name')
    ordering = ('user__username', 'folder__share_name', 'sub_path')
