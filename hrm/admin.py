from django.contrib import admin

from hrm.models import UserGuide


@admin.register(UserGuide)
class UserGuideAdmin(admin.ModelAdmin):
    list_display = ('title', 'updated_at', 'updated_by')
    readonly_fields = ('updated_at', 'updated_by')

    def has_add_permission(self, request):
        return not UserGuide.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

