from django.contrib import admin

from company_trip.models import TripEmailTemplate, TripRegistration, TripSettings


@admin.register(TripSettings)
class TripSettingsAdmin(admin.ModelAdmin):
    list_display = ('title', 'destination', 'start_date', 'end_date', 'registration_open')


@admin.register(TripRegistration)
class TripRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'department_name', 'room_type', 'companion1_name',
        'companion_confirmed', 'relative_full_name', 'room_key',
        'status', 'created_at',
    )
    list_filter = ('status', 'room_type')
    search_fields = ('full_name', 'email', 'phone', 'room_key')
    raw_id_fields = ('profile', 'user', 'companion1', 'companion2')


@admin.register(TripEmailTemplate)
class TripEmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('subject', 'updated_at')
