from django.contrib import admin

from company_trip.models import SpinNumber, TripEmailTemplate, TripRegistration, TripSettings


@admin.register(TripSettings)
class TripSettingsAdmin(admin.ModelAdmin):
    list_display = ('title', 'destination', 'start_date', 'end_date', 'registration_open')


@admin.register(TripRegistration)
class TripRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'department_name', 'room_type', 'room_key',
        'status', 'created_at',
    )
    list_filter = ('status', 'room_type', 'vegetarian')
    search_fields = ('full_name', 'email', 'phone', 'room_key')
    raw_id_fields = ('profile', 'user', 'companion1', 'companion2')


@admin.register(TripEmailTemplate)
class TripEmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('subject', 'updated_at')


@admin.register(SpinNumber)
class SpinNumberAdmin(admin.ModelAdmin):
    list_display = ('number', 'lucky', 'shown')
    list_filter = ('lucky', 'shown')
    search_fields = ('number',)
