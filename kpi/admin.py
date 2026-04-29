from django.contrib import admin
from django import forms
from .models import KpiPeriod, YearlyKpi, YearlyKpiItem

# =========================================================
# 1. QUẢN LÝ KỲ ĐÁNH GIÁ (DÙNG ĐỂ ĐIỀU KHIỂN ĐÓNG/MỞ CỘT)
# =========================================================
@admin.register(KpiPeriod)
class KpiPeriodAdmin(admin.ModelAdmin):
    # CẬP NHẬT DÒNG NÀY: Phải có 'is_active' thì mới dùng 'list_editable' được
    list_display = ('title', 'year', 'period_type', 'is_active', 'is_active_badge') 
    
    list_filter = ('year', 'period_type', 'is_active')
    
    # Trường này giờ đã hợp lệ vì nó đã nằm trong list_display ở trên
    list_editable = ('is_active',) 
    
    search_fields = ('title',)

    def is_active_badge(self, obj):
        from django.utils.html import format_html
        if obj.is_active:
            return format_html('<span style="color: #198754; font-weight: bold;">[ ĐANG MỞ ]</span>')
        return format_html('<span style="color: #6c757d;">[ ĐANG KHÓA ]</span>')
    is_active_badge.short_description = "Ghi chú trạng thái"
# =========================================================
# 2. QUẢN LÝ CÁC DÒNG KPI CHI TIẾT (INLINE)
# =========================================================
class YearlyKpiItemInline(admin.TabularInline):
    model = YearlyKpiItem
    extra = 0
    # Phân nhóm các trường để Admin dễ nhìn trong bảng chi tiết
    fieldsets = (
        ('Thông tin mục tiêu', {
            'fields': ('pillar', 'personal_objective', 'kpi_indicator', 'weightage', 'yearly_target', 'unit')
        }),
        ('Điểm số Quý 1', {'fields': ('q1_self', 'q1_mgr', 'q1_gm')}),
        ('Điểm số Quý 2', {'fields': ('q2_self', 'q2_mgr', 'q2_gm')}),
        ('Điểm số Quý 3', {'fields': ('q3_self', 'q3_mgr', 'q3_gm')}),
        ('Điểm số Quý 4', {'fields': ('q4_self', 'q4_mgr', 'q4_gm')}),
    )

# =========================================================
# 3. QUẢN LÝ BẢNG KPI TỔNG
# =========================================================
@admin.register(YearlyKpi)
class YearlyKpiAdmin(admin.ModelAdmin):
    list_display = ('employee_name', 'year', 'eval_type', 'q1_status_badge', 'q2_status_badge', 'q3_status_badge', 'q4_status_badge')
    list_filter = ('year', 'eval_type')
    search_fields = ('employee__username', 'employee__profile__full_name')
    autocomplete_fields = ('employee', 'direct_manager', 'general_manager')
    inlines = [YearlyKpiItemInline]

    # Hiển thị tên đầy đủ nhân viên thay vì username
    def employee_name(self, obj):
        return obj.employee.profile.full_name if hasattr(obj.employee, 'profile') else obj.employee.username
    employee_name.short_description = "Nhân viên"

    # Hiển thị Badge cho trạng thái từng quý
    def _get_status_html(self, status):
        from django.utils.html import format_html
        colors = {
            'self_evaluating': '#0dcaf0',      # Cyan
            'manager_evaluating': '#ffc107',   # Vàng
            'general_evaluating': '#dc3545',   # Đỏ
            'completed': '#198754'             # Xanh lá
        }
        labels = {
            'self_evaluating': 'NV',
            'manager_evaluating': 'HOD',
            'general_evaluating': 'GM',
            'completed': 'XONG'
        }
        color = colors.get(status, '#6c757d')
        label = labels.get(status, status)
        return format_html('<span style="background: {}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;">{}</span>', color, label)

    def q1_status_badge(self, obj): return self._get_status_html(obj.q1_status)
    q1_status_badge.short_description = "Q1"

    def q2_status_badge(self, obj): return self._get_status_html(obj.q2_status)
    q2_status_badge.short_description = "Q2"

    def q3_status_badge(self, obj): return self._get_status_html(obj.q3_status)
    q3_status_badge.short_description = "Q3"

    def q4_status_badge(self, obj): return self._get_status_html(obj.q4_status)
    q4_status_badge.short_description = "Q4"

    # Phân nhóm các trường trong trang sửa YearlyKpi
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('employee', 'year', 'eval_type')
        }),
        ('Phân cấp quản lý', {
            'fields': ('direct_manager', 'general_manager')
        }),
        ('Trạng thái luồng (Quý)', {
            'fields': (('q1_status', 'q2_status'), ('q3_status', 'q4_status')),
            'description': 'Thay đổi trạng thái này sẽ điều khiển quyền nộp bài của nhân viên và sếp.'
        }),
        ('Trạng thái luồng (Kỳ)', {
            'fields': (('h1_status', 'h2_status'),),
            'classes': ('collapse',), # Ẩn đi mặc định cho gọn
        }),
    )