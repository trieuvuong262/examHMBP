from django.conf import settings
from django.db import models
from django.utils import timezone


def current_year():
    return timezone.now().year


def current_month():
    return timezone.now().month


class MonthlyKpi(models.Model):
    """Bảng KPI theo tháng — một nhân viên / một tháng."""

    RESULT_FAIL = 'fail'
    RESULT_PASS = 'pass'
    RESULT_EXCEED = 'exceed'
    RESULT_PENDING = 'pending'

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='monthly_kpis',
        verbose_name='Nhân viên',
    )
    direct_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_monthly_kpis',
        verbose_name='Quản lý',
    )
    year = models.PositiveIntegerField(default=current_year, verbose_name='Năm')
    month = models.PositiveSmallIntegerField(default=current_month, verbose_name='Tháng')
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imported_monthly_kpis',
    )
    imported_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'year', 'month'],
                name='kpi_monthlykpi_employee_year_month_uniq',
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1, month__lte=12),
                name='kpi_monthlykpi_month_1_12',
            ),
        ]
        ordering = ['-year', '-month', 'employee_id']
        verbose_name = 'KPI tháng'
        verbose_name_plural = 'KPI tháng'

    def __str__(self):
        return f"KPI {self.month:02d}/{self.year} — {self.employee}"

    @property
    def period_label(self) -> str:
        return f'{self.month:02d}/{self.year}'

    def total_score(self) -> float | None:
        """Tổng điểm thành phần — ưu tiên điểm QL, chưa có thì dùng điểm NV."""
        total = 0.0
        has_any = False
        for item in self.items.all():
            part = item.component_score()
            if part is None:
                continue
            has_any = True
            total += part
        return round(total, 2) if has_any else None

    def result_code(self) -> str:
        score = self.total_score()
        if score is None:
            return self.RESULT_PENDING
        if score < 90:
            return self.RESULT_FAIL
        if score <= 100:
            return self.RESULT_PASS
        return self.RESULT_EXCEED

    def result_label(self) -> str:
        return {
            self.RESULT_FAIL: 'Không đạt',
            self.RESULT_PASS: 'Đạt',
            self.RESULT_EXCEED: 'Vượt',
            self.RESULT_PENDING: 'Chưa chấm',
        }.get(self.result_code(), 'Chưa chấm')

    def self_scored(self) -> bool:
        cache = getattr(self, '_prefetched_objects_cache', None)
        if cache is not None and 'items' in cache:
            return any(item.self_score is not None for item in cache['items'])
        return self.items.exclude(self_score__isnull=True).exists()

    def manager_scored(self) -> bool:
        cache = getattr(self, '_prefetched_objects_cache', None)
        if cache is not None and 'items' in cache:
            return any(item.mgr_score is not None for item in cache['items'])
        return self.items.exclude(mgr_score__isnull=True).exists()


class MonthlyKpiItem(models.Model):
    """Một tiêu chí KPI trong bảng tháng."""

    monthly_kpi = models.ForeignKey(
        MonthlyKpi,
        on_delete=models.CASCADE,
        related_name='items',
    )
    sort_order = models.PositiveIntegerField(default=1)
    work_group = models.CharField(max_length=255, blank=True, default='', verbose_name='Nhóm công việc')
    weightage = models.FloatField(default=0.0, verbose_name='Trọng số')
    indicator = models.TextField(verbose_name='Tiêu chí đo lường')
    level_fail = models.TextField(blank=True, default='', verbose_name='Mức chưa đạt')
    level_pass = models.TextField(blank=True, default='', verbose_name='Mức đạt')
    level_exceed = models.TextField(blank=True, default='', verbose_name='Mức vượt')

    self_actual = models.TextField(blank=True, default='', verbose_name='Đánh giá thực tế (NV)')
    self_score = models.FloatField(null=True, blank=True, verbose_name='Điểm NV')
    mgr_actual = models.TextField(blank=True, default='', verbose_name='Đánh giá thực tế (QL)')
    mgr_score = models.FloatField(null=True, blank=True, verbose_name='Điểm QL')

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Tiêu chí KPI tháng'
        verbose_name_plural = 'Tiêu chí KPI tháng'

    def __str__(self):
        text = (self.indicator or '')[:40]
        return f'{self.sort_order}. {text}'

    def effective_score(self) -> float | None:
        if self.mgr_score is not None:
            return float(self.mgr_score)
        if self.self_score is not None:
            return float(self.self_score)
        return None

    def component_score(self) -> float | None:
        score = self.effective_score()
        if score is None:
            return None
        return (score / 10.0) * float(self.weightage or 0)
