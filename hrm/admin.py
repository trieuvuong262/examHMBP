from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Permission, User

from hrm.models import (
    Department,
    DepartmentMenuPermission,
    DepartmentPosition,
    Division,
    DivisionPosition,
    PermissionGroup,
    Profile,
    ProfileConcurrentPosition,
    RoleModulePermission,
    UserGuide,
)


@admin.register(UserGuide)
class UserGuideAdmin(admin.ModelAdmin):
    list_display = ('title', 'updated_at', 'updated_by')
    readonly_fields = ('updated_at', 'updated_by')

    def has_add_permission(self, request):
        return not UserGuide.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# --- Cơ cấu tổ chức ---


class DepartmentPositionInline(admin.TabularInline):
    model = DepartmentPosition
    extra = 0
    fields = ('name', 'sort_order', 'is_active')


class DivisionInline(admin.TabularInline):
    model = Division
    extra = 0
    fields = ('name', 'sort_order', 'is_active')
    show_change_link = True


class DepartmentMenuPermissionInline(admin.StackedInline):
    model = DepartmentMenuPermission
    extra = 0
    max_num = 1
    can_delete = True
    fields = ('modules', 'updated_at')
    readonly_fields = ('updated_at',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'report_profile', 'sort_order', 'is_active', 'employee_count_display')
    list_filter = ('is_active', 'report_profile')
    search_fields = ('name',)
    list_editable = ('sort_order', 'is_active')
    inlines = [DivisionInline, DepartmentPositionInline, DepartmentMenuPermissionInline]

    @admin.display(description='Số NV')
    def employee_count_display(self, obj):
        return obj.employee_count


class DivisionPositionInline(admin.TabularInline):
    model = DivisionPosition
    extra = 0
    fields = ('name', 'sort_order', 'is_active')


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'sort_order', 'is_active', 'employee_count_display')
    list_filter = ('is_active', 'department')
    search_fields = ('name', 'department__name')
    list_editable = ('sort_order', 'is_active')
    list_select_related = ('department',)
    inlines = [DivisionPositionInline]

    @admin.display(description='Số NV')
    def employee_count_display(self, obj):
        return obj.employee_count


@admin.register(DepartmentPosition)
class DepartmentPositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'sort_order', 'is_active')
    list_filter = ('is_active', 'department')
    search_fields = ('name', 'department__name')
    list_select_related = ('department',)


@admin.register(DivisionPosition)
class DivisionPositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'division', 'department', 'sort_order', 'is_active')
    list_filter = ('is_active', 'department')
    search_fields = ('name', 'division__name', 'department__name')
    list_select_related = ('division', 'department')


# --- Phân quyền ---


@admin.register(PermissionGroup)
class PermissionGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_system', 'member_count', 'updated_at')
    list_filter = ('is_system',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('updated_at',)

    @admin.display(description='Số thành viên')
    def member_count(self, obj):
        return obj.profiles.count()

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(RoleModulePermission)
class RoleModulePermissionAdmin(admin.ModelAdmin):
    list_display = ('role', 'updated_at')
    readonly_fields = ('updated_at',)


@admin.register(DepartmentMenuPermission)
class DepartmentMenuPermissionAdmin(admin.ModelAdmin):
    list_display = ('department', 'updated_at')
    search_fields = ('department__name',)
    readonly_fields = ('updated_at',)
    list_select_related = ('department',)


# --- Hồ sơ nhân viên ---


class ProfileConcurrentPositionInline(admin.StackedInline):
    model = ProfileConcurrentPosition
    extra = 0
    classes = ('collapse',)
    autocomplete_fields = ('department', 'division')
    filter_horizontal = ('subordinates',)
    fields = (
        ('department', 'division'),
        ('job_position', 'job_title', 'role'),
        ('sort_order', 'is_active'),
        'notes',
        'subordinates',
    )


_PROFILE_FIELDSETS = (
    ('Thông tin nhân sự', {
        'fields': (
            ('employee_code', 'full_name'),
            ('phone', 'gender', 'date_of_birth'),
            'avatar',
        ),
    }),
    ('Công việc', {
        'fields': (
            ('department', 'division'),
            ('job_position', 'job_title'),
            ('join_date', 'on_probation', 'is_employed'),
        ),
    }),
    ('Phân quyền', {
        'fields': (
            ('role', 'permission_group'),
            'subordinates',
            'must_change_password',
        ),
    }),
    ('Odoo', {
        'classes': ('collapse',),
        'fields': (('odoo_user_id', 'odoo_password_synced'),),
    }),
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'employee_code', 'full_name', 'user', 'department', 'division',
        'job_position', 'role', 'permission_group', 'is_employed', 'on_probation',
    )
    list_display_links = ('employee_code', 'full_name')
    list_filter = ('is_employed', 'on_probation', 'role', 'department', 'permission_group', 'gender')
    search_fields = (
        'employee_code', 'full_name', 'phone',
        'user__username', 'user__email', 'job_position', 'job_title',
    )
    list_select_related = ('user', 'department', 'division', 'permission_group')
    autocomplete_fields = ('department', 'division', 'permission_group')
    raw_id_fields = ('user',)
    filter_horizontal = ('subordinates',)
    fieldsets = (('Tài khoản', {'fields': ('user',)}),) + _PROFILE_FIELDSETS
    inlines = [ProfileConcurrentPositionInline]
    list_per_page = 50


@admin.register(ProfileConcurrentPosition)
class ProfileConcurrentPositionAdmin(admin.ModelAdmin):
    list_display = ('profile', 'department', 'division', 'job_position', 'job_title', 'role', 'is_active')
    list_filter = ('is_active', 'role', 'department')
    search_fields = ('profile__full_name', 'profile__employee_code', 'job_position', 'job_title')
    list_select_related = ('profile', 'department', 'division')
    raw_id_fields = ('profile',)
    autocomplete_fields = ('department', 'division')
    filter_horizontal = ('subordinates',)


# --- Tài khoản đăng nhập: gắn hồ sơ nhân viên vào trang User ---


class ProfileInline(admin.StackedInline):
    model = Profile
    fk_name = 'user'
    can_delete = False
    verbose_name_plural = 'Hồ sơ nhân viên'
    autocomplete_fields = ('department', 'division', 'permission_group')
    filter_horizontal = ('subordinates',)
    fieldsets = _PROFILE_FIELDSETS


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'codename', 'content_type')
    list_filter = ('content_type__app_label',)
    search_fields = ('name', 'codename', 'content_type__app_label', 'content_type__model')
    list_select_related = ('content_type',)


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        'username', 'profile_full_name', 'profile_employee_code', 'email',
        'profile_department', 'is_active', 'is_staff', 'last_login',
    )
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'profile__department', 'profile__role', 'groups')
    search_fields = (
        'username', 'first_name', 'last_name', 'email',
        'profile__full_name', 'profile__employee_code', 'profile__phone',
    )
    list_select_related = ('profile', 'profile__department')

    def get_inlines(self, request, obj=None):
        # Signal post_save của User tự tạo Profile; inline ở form thêm mới sẽ tạo trùng.
        return [ProfileInline] if obj is not None else []

    @admin.display(description='Họ và tên', ordering='profile__full_name')
    def profile_full_name(self, obj):
        return getattr(getattr(obj, 'profile', None), 'full_name', '') or '—'

    @admin.display(description='Mã NS', ordering='profile__employee_code')
    def profile_employee_code(self, obj):
        return getattr(getattr(obj, 'profile', None), 'employee_code', '') or '—'

    @admin.display(description='Phòng ban', ordering='profile__department__name')
    def profile_department(self, obj):
        dept = getattr(getattr(obj, 'profile', None), 'department', None)
        return dept or '—'
