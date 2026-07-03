import os

from django.conf import settings
from django.db import models

from reports.period_utils import PERIOD_CHOICES, PERIOD_DAY
from reports.report_profile import (
    REPORT_PROFILE_CHOICES,
    REPORT_PROFILE_OFFICE,
    REPORT_PROFILE_PRODUCTION,
)
from reports.daily_nas_storage import DailyReportNasStorage, daily_attachment_upload_to
from reports.weekly_nas_storage import WeeklyReportNasStorage, weekly_attachment_upload_to


class DailyWorkReport(models.Model):
    SHIFT_MORNING = 'MORNING'
    SHIFT_OVERTIME = 'OVERTIME'
    SHIFT_NIGHT = 'NIGHT'
    SHIFT_CHOICES = [
        (SHIFT_MORNING, 'Ca sáng'),
        (SHIFT_OVERTIME, 'Tăng ca'),
        (SHIFT_NIGHT, 'Ca tối'),
    ]

    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_SUBMITTED, 'Đã nộp'),
    ]

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_work_reports',
        verbose_name='Nhân viên',
    )
    report_date = models.DateField(verbose_name='Ngày báo cáo')
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default=SHIFT_MORNING, blank=True)
    title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Tiêu đề báo cáo',
        help_text='Dùng cho báo cáo tuần / tháng.',
    )
    report_profile = models.CharField(
        max_length=20,
        choices=REPORT_PROFILE_CHOICES,
        default=REPORT_PROFILE_PRODUCTION,
        verbose_name='Loại báo cáo',
    )
    spreadsheet_json = models.JSONField(null=True, blank=True, verbose_name='Bảng Excel (JSON)')
    document_html = models.TextField(blank=True, verbose_name='Văn bản Word (HTML)')
    links = models.TextField(blank=True, verbose_name='Link (mỗi dòng một link)')
    report_period = models.CharField(
        max_length=10,
        choices=PERIOD_CHOICES,
        default=PERIOD_DAY,
        verbose_name='Chu kỳ',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    draft_saved_at = models.DateTimeField(null=True, blank=True, verbose_name='Lưu nháp lúc')
    hod_reviewed = models.BooleanField(default=False, verbose_name='HOD đã xem')
    hod_note = models.CharField(max_length=500, blank=True, verbose_name='Ghi chú HOD')
    shift_started_at = models.DateTimeField(null=True, blank=True, verbose_name='Bắt đầu ca')
    proxy_entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='proxy_daily_reports_entered',
        verbose_name='Tổ trưởng nhập hộ',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-report_date', '-updated_at']
        unique_together = ('employee', 'report_date', 'report_profile', 'report_period', 'shift')
        verbose_name = 'Báo cáo công việc ngày'
        verbose_name_plural = 'Báo cáo công việc ngày'

    def __str__(self):
        return f'{self.employee} - {self.report_date}'

    @property
    def link_lines(self):
        from reports.link_utils import parse_link_lines
        return parse_link_lines(self.links or '')

    @property
    def is_production_report(self):
        return self.report_profile == REPORT_PROFILE_PRODUCTION

    @property
    def is_proxy_entered(self):
        return self.proxy_entered_by_id is not None

    @property
    def is_edit_expired(self):
        from reports.report_lock import is_report_edit_expired
        return is_report_edit_expired(self)

    @property
    def last_editable_on(self):
        from reports.report_lock import last_editable_date
        return last_editable_date(self)

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())


class DailyWorkReportAttachment(models.Model):
    SOURCE_BANG = 'BANG'
    SOURCE_VANBAN = 'VANBAN'
    SOURCE_LINK = 'LINK'
    SOURCE_TAB_CHOICES = [
        (SOURCE_BANG, 'Bảng'),
        (SOURCE_VANBAN, 'Văn bản'),
        (SOURCE_LINK, 'Link'),
    ]

    KIND_FILE = 'FILE'
    KIND_IMAGE = 'IMAGE'
    KIND_CHOICES = [
        (KIND_FILE, 'File'),
        (KIND_IMAGE, 'Ảnh'),
    ]

    report = models.ForeignKey(
        DailyWorkReport,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Báo cáo ngày',
    )
    source_tab = models.CharField(max_length=10, choices=SOURCE_TAB_CHOICES)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    file = models.FileField(
        upload_to=daily_attachment_upload_to,
        storage=DailyReportNasStorage(),
    )
    original_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'Đính kèm báo cáo ngày'
        verbose_name_plural = 'Đính kèm báo cáo ngày'

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.original_name or os.path.basename(self.file.name)

    @property
    def file_url(self):
        from django.urls import reverse
        if not self.pk:
            return ''
        return reverse('reports:daily_attachment', kwargs={'pk': self.pk})

    @property
    def is_image(self):
        return self.kind == self.KIND_IMAGE


class DailyWorkReportLine(models.Model):
    AREA_CUT = 'CUT'
    AREA_SEW = 'SEW'
    AREA_PRINT = 'PRINT'
    AREA_PACK = 'PACK'
    AREA_QC = 'QC'
    AREA_WH = 'WH'
    AREA_PLAN = 'PLAN'
    AREA_TECH = 'TECH'
    AREA_OTHER = 'OTHER'
    AREA_CHOICES = [
        (AREA_CUT, 'Cắt vải'),
        (AREA_SEW, 'May'),
        (AREA_PRINT, 'In/Thêu'),
        (AREA_PACK, 'Gói đóng'),
        (AREA_QC, 'Kiểm QC'),
        (AREA_WH, 'Kho'),
        (AREA_PLAN, 'KHSX'),
        (AREA_TECH, 'Kỹ thuật/Rập'),
        (AREA_OTHER, 'Khác'),
    ]

    UNIT_PCS = 'PCS'
    UNIT_SET = 'SET'
    UNIT_M = 'M'
    UNIT_KG = 'KG'
    UNIT_CHOICES = [
        (UNIT_PCS, 'Cái'),
        (UNIT_SET, 'Bộ'),
        (UNIT_M, 'Mét'),
        (UNIT_KG, 'Kg'),
    ]

    report = models.ForeignKey(
        DailyWorkReport,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Báo cáo',
    )
    area = models.CharField(max_length=20, choices=AREA_CHOICES, verbose_name='Công đoạn')
    order_code = models.CharField(max_length=80, blank=True, verbose_name='Mã đơn/Style')
    product_name = models.CharField(max_length=120, blank=True, verbose_name='Tên SP')
    quantity = models.PositiveIntegerField(default=0, verbose_name='Sản lượng')
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default=UNIT_PCS, verbose_name='ĐVT')
    note = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú ngắn')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Dòng công việc'
        verbose_name_plural = 'Dòng công việc'

    def __str__(self):
        return f'{self.get_area_display()} - {self.order_code or self.product_name}'


class ProductionShiftProduct(models.Model):
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_DONE = 'DONE'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Đang làm'),
        (STATUS_DONE, 'Đã kết thúc'),
    ]

    report = models.ForeignKey(
        DailyWorkReport,
        on_delete=models.CASCADE,
        related_name='production_products',
        verbose_name='Báo cáo',
    )
    product_code = models.CharField(max_length=80, blank=True, default='', verbose_name='Mã hàng')
    process_name = models.CharField(max_length=120, blank=True, default='', verbose_name='Tên công đoạn')
    norm_per_hour = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Định mức 1 giờ',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    sort_order = models.PositiveSmallIntegerField(default=0)
    first_slot_index = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='Khung giờ bắt đầu phiên mã hàng',
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Bắt đầu công đoạn')
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name='Kết thúc công đoạn')
    total_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Tổng sản lượng phiên',
    )
    total_damaged_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name='Tổng hư hỏng phiên',
    )
    completion_note = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Ghi chú phiên',
    )

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Mã hàng trong ca'
        verbose_name_plural = 'Mã hàng trong ca'

    def __str__(self):
        label = self.product_code or 'Đang nhập'
        return f'{label} — {self.process_name or "…"}'


class ProductionHourlyQuantity(models.Model):
    product = models.ForeignKey(
        ProductionShiftProduct,
        on_delete=models.CASCADE,
        related_name='hourly_entries',
        verbose_name='Mã hàng',
    )
    slot_index = models.PositiveSmallIntegerField(verbose_name='Khung giờ')
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Sản lượng giờ',
    )
    damaged_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name='Số lượng hư hỏng',
    )
    note = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Ghi chú',
    )
    partial_hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Giờ thực tế (khi chia giờ)',
    )
    zero_reason = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Lý do sản lượng 0',
    )

    class Meta:
        ordering = ['slot_index']
        unique_together = ('product', 'slot_index')
        verbose_name = 'Sản lượng theo giờ'
        verbose_name_plural = 'Sản lượng theo giờ'

    def __str__(self):
        return f'slot {self.slot_index}: {self.quantity}'


class WeeklyWorkReport(models.Model):
    STATUS_DRAFT = DailyWorkReport.STATUS_DRAFT
    STATUS_SUBMITTED = DailyWorkReport.STATUS_SUBMITTED
    STATUS_CHOICES = DailyWorkReport.STATUS_CHOICES

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='weekly_work_reports',
        verbose_name='Nhân viên',
    )
    week_start = models.DateField(verbose_name='Tuần (thứ 2)')
    report_profile = models.CharField(
        max_length=20,
        choices=REPORT_PROFILE_CHOICES,
        default=REPORT_PROFILE_OFFICE,
        verbose_name='Loại báo cáo',
    )
    links = models.TextField(blank=True, verbose_name='Link (mỗi dòng một link)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    draft_saved_at = models.DateTimeField(null=True, blank=True, verbose_name='Lưu nháp lúc')
    hod_reviewed = models.BooleanField(default=False, verbose_name='HOD đã xem')
    hod_note = models.CharField(max_length=500, blank=True, verbose_name='Ghi chú HOD')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-week_start', '-updated_at']
        unique_together = ('employee', 'week_start')
        verbose_name = 'Báo cáo công việc tuần'
        verbose_name_plural = 'Báo cáo công việc tuần'

    def __str__(self):
        return f'{self.employee} - tuần {self.week_start}'

    @property
    def is_production_report(self):
        return self.report_profile == REPORT_PROFILE_PRODUCTION

    @property
    def link_lines(self):
        from reports.link_utils import parse_link_lines
        return parse_link_lines(self.links or '')

    @property
    def week_range_label(self):
        from reports.week_utils import week_label
        return week_label(self.week_start)

    @property
    def is_edit_expired(self):
        from reports.report_lock import is_report_edit_expired
        return is_report_edit_expired(self)

    @property
    def last_editable_on(self):
        from reports.report_lock import last_editable_date
        return last_editable_date(self)


class WeeklyWorkReportAttachment(models.Model):
    KIND_FILE = 'FILE'
    KIND_IMAGE = 'IMAGE'
    KIND_CHOICES = [
        (KIND_FILE, 'File'),
        (KIND_IMAGE, 'Ảnh'),
    ]

    report = models.ForeignKey(
        WeeklyWorkReport,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Báo cáo tuần',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    file = models.FileField(
        upload_to=weekly_attachment_upload_to,
        storage=WeeklyReportNasStorage(),
    )
    original_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'Đính kèm báo cáo tuần'
        verbose_name_plural = 'Đính kèm báo cáo tuần'

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.original_name or os.path.basename(self.file.name)

    @property
    def file_url(self):
        from django.urls import reverse
        if not self.pk:
            return ''
        return reverse('reports:weekly_attachment', kwargs={'pk': self.pk})

    @property
    def is_image(self):
        return self.kind == self.KIND_IMAGE


class ReportComment(models.Model):
    """Nhận xét/phản hồi hai chiều trên báo cáo — quản lý và nhân viên trao đổi qua lại."""

    daily_report = models.ForeignKey(
        DailyWorkReport,
        on_delete=models.CASCADE,
        related_name='comments',
        null=True,
        blank=True,
        verbose_name='Báo cáo ngày',
    )
    weekly_report = models.ForeignKey(
        WeeklyWorkReport,
        on_delete=models.CASCADE,
        related_name='comments',
        null=True,
        blank=True,
        verbose_name='Báo cáo tuần',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='report_comments',
        verbose_name='Người nhận xét',
    )
    body = models.TextField(verbose_name='Nội dung nhận xét')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'Nhận xét báo cáo'
        verbose_name_plural = 'Nhận xét báo cáo'

    def __str__(self):
        return f'{self.author} · {self.created_at:%d/%m/%Y %H:%M}'
