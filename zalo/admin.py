from django.contrib import admin

from zalo.models import PasswordResetOtp, ZaloOAuthToken


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


@admin.register(PasswordResetOtp)
class PasswordResetOtpAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'phone', 'status', 'attempts', 'expires_at', 'created_at',
    )
    list_filter = ('status',)
    search_fields = ('user__username', 'phone', 'session_token')
    readonly_fields = (
        'user', 'code_hash', 'session_token', 'phone', 'ip_address',
        'attempts', 'status', 'expires_at', 'verified_at', 'used_at', 'created_at',
    )

    def has_add_permission(self, request):
        return False
