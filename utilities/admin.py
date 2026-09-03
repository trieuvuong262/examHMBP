from django.contrib import admin

from utilities.models import (
    MealDayOffering,
    MealDish,
    MealEligibleEmployee,
    MealOrder,
    MealOrderDecline,
    MealOrderSettings,
    SalaryAdvanceDecline,
    SalaryAdvanceRequest,
    SalaryAdvanceSettings,
    ScheduleReminder,
    ScheduleReminderPushLog,
)


@admin.register(MealOrderSettings)
class MealOrderSettingsAdmin(admin.ModelAdmin):
    list_display = ('order_start_time', 'order_end_time', 'order_days_before', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not MealOrderSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SalaryAdvanceSettings)
class SalaryAdvanceSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'is_enabled',
        'open_day_start',
        'open_time_start',
        'open_day_end',
        'open_time_end',
        'max_amount',
        'updated_at',
    )

    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not SalaryAdvanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MealDish)
class MealDishAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    list_editable = ('sort_order', 'is_active')
    ordering = ('sort_order', 'name')

    def get_readonly_fields(self, request, obj=None):
        if obj and MealOrder.objects.filter(dish=obj).exists():
            return ('name',)
        return ()


@admin.register(MealDayOffering)
class MealDayOfferingAdmin(admin.ModelAdmin):
    list_display = ('meal_date', 'dish', 'dish_name', 'is_offered')
    list_filter = ('is_offered', 'meal_date')
    search_fields = ('dish__name', 'dish_name')
    list_select_related = ('dish',)
    autocomplete_fields = ('dish',)
    date_hierarchy = 'meal_date'
    ordering = ('-meal_date', 'dish__sort_order')
    readonly_fields = ('dish_name',)


@admin.register(MealEligibleEmployee)
class MealEligibleEmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee', 'created_at', 'updated_at')
    search_fields = (
        'employee__username',
        'employee__profile__full_name',
    )
    list_select_related = ('employee', 'employee__profile')
    raw_id_fields = ('employee',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('employee__username',)


@admin.register(MealOrder)
class MealOrderAdmin(admin.ModelAdmin):
    list_display = ('meal_date', 'employee', 'dish', 'dish_name', 'note', 'created_at')
    list_filter = ('meal_date', 'dish')
    search_fields = (
        'employee__username',
        'employee__profile__full_name',
        'dish__name',
        'dish_name',
        'note',
    )
    list_select_related = ('employee', 'employee__profile', 'dish')
    raw_id_fields = ('employee',)
    autocomplete_fields = ('dish',)
    date_hierarchy = 'meal_date'
    readonly_fields = ('dish_name', 'created_at', 'updated_at')
    ordering = ('-meal_date', '-created_at')


@admin.register(MealOrderDecline)
class MealOrderDeclineAdmin(admin.ModelAdmin):
    list_display = ('meal_date', 'employee', 'created_at')
    list_filter = ('meal_date',)
    search_fields = (
        'employee__username',
        'employee__profile__full_name',
    )
    list_select_related = ('employee', 'employee__profile')
    raw_id_fields = ('employee',)
    date_hierarchy = 'meal_date'
    readonly_fields = ('created_at',)
    ordering = ('-meal_date', '-created_at')


@admin.register(SalaryAdvanceRequest)
class SalaryAdvanceRequestAdmin(admin.ModelAdmin):
    list_display = ('request_month', 'employee', 'amount', 'note', 'created_at')
    list_filter = ('request_month',)
    search_fields = (
        'employee__username',
        'employee__profile__full_name',
        'note',
    )
    list_select_related = ('employee', 'employee__profile')
    raw_id_fields = ('employee',)
    date_hierarchy = 'request_month'
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-request_month', '-created_at')

    def save_model(self, request, obj, form, change):
        from utilities.models import normalize_request_month
        obj.request_month = normalize_request_month(obj.request_month)
        super().save_model(request, obj, form, change)


@admin.register(SalaryAdvanceDecline)
class SalaryAdvanceDeclineAdmin(admin.ModelAdmin):
    list_display = ('request_month', 'employee', 'created_at')
    list_filter = ('request_month',)
    search_fields = (
        'employee__username',
        'employee__profile__full_name',
    )
    list_select_related = ('employee', 'employee__profile')
    raw_id_fields = ('employee',)
    date_hierarchy = 'request_month'
    readonly_fields = ('created_at',)
    ordering = ('-request_month', '-created_at')


@admin.register(ScheduleReminder)
class ScheduleReminderAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'repeat_mode', 'remind_time', 'once_date', 'is_active')
    list_filter = ('is_active', 'repeat_mode')
    search_fields = ('title', 'body', 'user__username')
    raw_id_fields = ('user',)
    ordering = ('-created_at',)


@admin.register(ScheduleReminderPushLog)
class ScheduleReminderPushLogAdmin(admin.ModelAdmin):
    list_display = ('reminder', 'fire_date', 'sent_at')
    list_filter = ('fire_date',)
    raw_id_fields = ('reminder',)
    ordering = ('-sent_at',)
