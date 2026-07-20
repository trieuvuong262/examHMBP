from django.contrib import admin

from zalo.models import ZaloOAuthToken


@admin.register(ZaloOAuthToken)
class ZaloOAuthTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'has_access', 'has_refresh', 'expires_at', 'updated_at')
    readonly_fields = ('updated_at',)

    @admin.display(boolean=True, description='access')
    def has_access(self, obj):
        return bool(obj.access_token)

    @admin.display(boolean=True, description='refresh')
    def has_refresh(self, obj):
        return bool(obj.refresh_token)

    def has_add_permission(self, request):
        return not ZaloOAuthToken.objects.exists()
