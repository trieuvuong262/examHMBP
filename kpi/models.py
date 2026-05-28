from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

def current_year():
    return timezone.now().year

# =========================================================
# 1. KỲ ĐÁNH GIÁ (ADMIN DÙNG ĐỂ MỞ/KHÓA CỘT TRÊN FORM)
# =========================================================
class KpiPeriod(models.Model):
    PERIOD_CHOICES = [
        ('Q1', 'Quý 1'), ('Q2', 'Quý 2'), ('Q3', 'Quý 3'), ('Q4', 'Quý 4'),
        ('H1', 'Sáu tháng đầu năm (H1)'), ('H2', 'Sáu tháng cuối năm (H2)'),
        ('Y', 'Cả năm (Y)'),
    ]
    
    title = models.CharField(max_length=255, verbose_name="Tên kỳ")
    year = models.IntegerField(verbose_name="Năm", default=current_year)
    period_type = models.CharField(max_length=2, choices=PERIOD_CHOICES, verbose_name="Loại kỳ")
    is_active = models.BooleanField(default=False, verbose_name="Admin cho phép chấm điểm")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['year', 'period_type'],
                name='kpi_kpiperiod_year_period_type_uniq',
            ),
        ]

    def __str__(self):
        status = "ĐANG MỞ" if self.is_active else "ĐANG KHÓA"
        return f"{self.title} ({self.year}) - {status}"

# =========================================================
# 2. BẢNG KPI TỔNG: QUẢN LÝ MỤC TIÊU VÀ TRẠNG THÁI LUỒNG
# =========================================================
class YearlyKpi(models.Model):
    EVAL_TYPE_CHOICES = [
        ('QUARTER', 'Đánh giá theo Quý (4 cột)'),
        ('HALF', 'Đánh giá theo Kỳ (2 cột)'),
        ('YEAR', 'Đánh giá Cả năm (1 cột)'), # <--- THÊM DÒNG NÀY
    ]
    STATUS_CHOICES = [
        ('self_evaluating', 'Đang làm'),
        ('manager_evaluating', 'HOD Đang chấm'),
        ('general_evaluating', 'GM Đang chấm'),
        ('completed', 'Hoàn tất'),
    ]
    
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='yearly_kpis')
    year = models.IntegerField(default=current_year, verbose_name="Năm giao KPI")
    eval_type = models.CharField(max_length=10, choices=EVAL_TYPE_CHOICES, default='QUARTER', verbose_name="Chế độ hiển thị")
    direct_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_yearly_kpis')
    general_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gm_yearly_kpis')

    q1_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='self_evaluating')
    q2_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='self_evaluating')
    q3_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='self_evaluating')
    q4_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='self_evaluating')
    h1_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='self_evaluating')
    h2_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='self_evaluating')
    y_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='self_evaluating')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'year')

    def __str__(self):
        return f"KPI {self.year} - {self.employee.username} ({self.get_eval_type_display()})"

# =========================================================
# 3. DÒNG KPI CHI TIẾT: CHỨA CẢ CHỈ TIÊU VÀ TẤT CẢ CÁC CỘT ĐIỂM
# =========================================================
class YearlyKpiItem(models.Model):
    PILLAR_CHOICES = [
        ('PEOPLE', 'Quản trị nguồn nhân lực'),
        ('FINANCE', 'Kết quả Tài chính'),
        ('CUSTOMER', 'Khách hàng/Bệnh nhân'),
        ('OPERATION', 'Vận hành - Công nghệ'),
    ]
    
    yearly_kpi = models.ForeignKey(YearlyKpi, on_delete=models.CASCADE, related_name='items')
    pillar = models.CharField(max_length=20, choices=PILLAR_CHOICES, default='OPERATION')
    personal_objective = models.TextField(verbose_name="Mục tiêu cá nhân")
    kpi_indicator = models.TextField(verbose_name="Chỉ số đo lường")
    weightage = models.FloatField(default=0.0, verbose_name="Trọng số (%)")
    yearly_target = models.FloatField(default=0.0, verbose_name="Chỉ tiêu năm")
    unit = models.CharField(max_length=20, default="%")
    trend = models.CharField(max_length=10, default='HIGHER')
    y_self = models.FloatField(null=True, blank=True)
    y_mgr = models.FloatField(null=True, blank=True)
    y_gm = models.FloatField(null=True, blank=True)
    # -------------------------------------------------------
    # CỘT ĐIỂM QUÝ (Nhân viên tự chấm)
    # -------------------------------------------------------
    q1_self = models.FloatField(null=True, blank=True, verbose_name="Điểm NV Q1")
    q2_self = models.FloatField(null=True, blank=True, verbose_name="Điểm NV Q2")
    q3_self = models.FloatField(null=True, blank=True, verbose_name="Điểm NV Q3")
    q4_self = models.FloatField(null=True, blank=True, verbose_name="Điểm NV Q4")

    # Điểm quản lý chấm (HOD)
    q1_mgr = models.FloatField(null=True, blank=True, verbose_name="HOD Q1")
    q2_mgr = models.FloatField(null=True, blank=True, verbose_name="HOD Q2")
    q3_mgr = models.FloatField(null=True, blank=True, verbose_name="HOD Q3")
    q4_mgr = models.FloatField(null=True, blank=True, verbose_name="HOD Q4")

    # Điểm quản lý chung chốt (GM)
    q1_gm = models.FloatField(null=True, blank=True, verbose_name="GM Q1")
    q2_gm = models.FloatField(null=True, blank=True, verbose_name="GM Q2")
    q3_gm = models.FloatField(null=True, blank=True, verbose_name="GM Q3")
    q4_gm = models.FloatField(null=True, blank=True, verbose_name="GM Q4")

    # -------------------------------------------------------
    # CỘT ĐIỂM KỲ (Bán niên)
    # -------------------------------------------------------
    h1_self = models.FloatField(null=True, blank=True, verbose_name="Điểm NV H1")
    h2_self = models.FloatField(null=True, blank=True, verbose_name="Điểm NV H2")
    
    h1_mgr = models.FloatField(null=True, blank=True, verbose_name="HOD H1")
    h2_mgr = models.FloatField(null=True, blank=True, verbose_name="HOD H2")

    h1_gm = models.FloatField(null=True, blank=True, verbose_name="GM H1")
    h2_gm = models.FloatField(null=True, blank=True, verbose_name="GM H2")

    def __str__(self):
        return f"{self.personal_objective[:30]}..."