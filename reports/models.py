import os

from django.conf import settings
from django.db import models

from reports.report_profile import (
    REPORT_PROFILE_CHOICES,
    REPORT_PROFILE_PRODUCTION,
)
from reports.weekly_nas_storage import WeeklyReportNasStorage, weekly_attachment_upload_to


class DailyWorkReport(models.Model):
    SHIFT_MORNING = 'MORNING'
    SHIFT_AFTERNOON = 'AFTERNOON'
    SHIFT_NIGHT = 'NIGHT'
    SHIFT_CHOICES = [
        (SHIFT_MORNING, 'Ca sáng'),
        (SHIFT_AFTERNOON, 'Ca chiều'),
        (SHIFT_NIGHT, 'Ca đêm'),
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
    report_profile = models.CharField(
        max_length=20,
        choices=REPORT_PROFILE_CHOICES,
        default=REPORT_PROFILE_PRODUCTION,
        verbose_name='Loại báo cáo',
    )
    spreadsheet_json = models.JSONField(null=True, blank=True, verbose_name='Bảng Excel (JSON)')
    document_html = models.TextField(blank=True, verbose_name='Văn bản Word (HTML)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    draft_saved_at = models.DateTimeField(null=True, blank=True, verbose_name='Lưu nháp lúc')
    hod_reviewed = models.BooleanField(default=False, verbose_name='HOD đã xem')
    hod_note = models.CharField(max_length=500, blank=True, verbose_name='Ghi chú HOD')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-report_date', '-updated_at']
        unique_together = ('employee', 'report_date')
        verbose_name = 'Báo cáo công việc ngày'
        verbose_name_plural = 'Báo cáo công việc ngày'

    def __str__(self):
        return f'{self.employee} - {self.report_date}'

    @property
    def is_production_report(self):
        return self.report_profile == REPORT_PROFILE_PRODUCTION

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())


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
    def link_lines(self):
        return [line.strip() for line in (self.links or '').splitlines() if line.strip()]

    @property
    def week_range_label(self):
        from reports.week_utils import week_label
        return week_label(self.week_start)


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
