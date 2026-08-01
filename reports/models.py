import os
from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from reports.period_utils import PERIOD_CHOICES, PERIOD_DAY
from reports.report_profile import (
    REPORT_PROFILE_CHOICES,
    REPORT_PROFILE_OFFICE,
    REPORT_PROFILE_PRODUCTION,
)
from reports.comment_nas_storage import ReportCommentNasStorage, comment_attachment_upload_to
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
        help_text='Tuỳ chọn với báo cáo ngày; bắt buộc khi nộp báo cáo tuần / tháng.',
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
    submit_clicked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Bấm gửi lúc',
        help_text=(
            'Thời điểm thật báo cáo chuyển sang Đã gửi. Ca tối hiển thị submitted_at theo lúc '
            'bắt đầu công đoạn đầu tiên, nên hạn duyệt / hạn sửa tính theo trường này.'
        ),
    )
    draft_saved_at = models.DateTimeField(null=True, blank=True, verbose_name='Lưu nháp lúc')
    hod_reviewed = models.BooleanField(default=False, verbose_name='HOD đã duyệt')
    hod_reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='HOD duyệt lúc')
    hod_first_reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Lần duyệt đầu tiên lúc',
    )
    hod_rejected = models.BooleanField(default=False, verbose_name='Không duyệt (quá hạn)')
    hod_rejected_at = models.DateTimeField(null=True, blank=True, verbose_name='Không duyệt lúc')
    hod_note = models.CharField(max_length=500, blank=True, verbose_name='Ghi chú HOD')
    declared_work_hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Thời gian làm việc (giờ)',
    )
    shift_started_at = models.DateTimeField(null=True, blank=True, verbose_name='Bắt đầu ca')
    proxy_entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='proxy_daily_reports_entered',
        verbose_name='Tổ trưởng nhập hộ',
    )
    auto_submitted = models.BooleanField(
        default=False,
        verbose_name='Hệ thống tự động gửi',
        help_text='True khi báo cáo được gửi tự động lúc 23:30 (không phải công nhân / tổ trưởng gửi).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-report_date', '-updated_at']
        unique_together = ('employee', 'report_date', 'report_profile', 'report_period', 'shift')
        verbose_name = 'Báo cáo công việc'
        verbose_name_plural = 'Báo cáo công việc'

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
    def is_hod_rejected(self):
        return bool(self.hod_rejected) and not self.hod_reviewed

    @property
    def is_edit_expired(self):
        from reports.report_lock import (
            is_production_employee_edit_expired,
            is_report_edit_expired,
        )
        if self.is_production_report:
            return is_production_employee_edit_expired(self)
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
        verbose_name='Báo cáo',
    )
    source_tab = models.CharField(max_length=10, choices=SOURCE_TAB_CHOICES)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    file = models.FileField(
        upload_to=daily_attachment_upload_to,
        storage=DailyReportNasStorage(),
        max_length=255,
    )
    original_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'Đính kèm báo cáo'
        verbose_name_plural = 'Đính kèm báo cáo'

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
    submitted_locked = models.BooleanField(
        default=False,
        verbose_name='Đã chốt khi gửi báo cáo',
        help_text='True = không sửa sau khi đã gửi báo cáo (kể cả «Nhập tiếp»).',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_products_updated',
        verbose_name='Cập nhật',
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
        verbose_name = 'Báo cáo tuần (sản xuất)'
        verbose_name_plural = 'Báo cáo tuần (sản xuất)'

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
        verbose_name = 'Đính kèm báo cáo tuần (SX)'
        verbose_name_plural = 'Đính kèm báo cáo tuần (SX)'

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
        verbose_name='Báo cáo',
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
    is_read = models.BooleanField(default=False, verbose_name='Đã đọc')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'Nhận xét báo cáo'
        verbose_name_plural = 'Nhận xét báo cáo'

    def __str__(self):
        return f'{self.author} · {self.created_at:%d/%m/%Y %H:%M}'


class ReportCommentAttachment(models.Model):
    KIND_FILE = 'FILE'
    KIND_IMAGE = 'IMAGE'
    KIND_CHOICES = [
        (KIND_FILE, 'File'),
        (KIND_IMAGE, 'Ảnh'),
    ]

    comment = models.ForeignKey(
        ReportComment,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Nhận xét',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    file = models.FileField(
        upload_to=comment_attachment_upload_to,
        storage=ReportCommentNasStorage(),
    )
    original_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'Đính kèm nhận xét'
        verbose_name_plural = 'Đính kèm nhận xét'

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
        return reverse('reports:comment_attachment', kwargs={'pk': self.pk})

    @property
    def is_image(self):
        return self.kind == self.KIND_IMAGE


class DailyWorkReportEditLog(models.Model):
    ACTOR_EMPLOYEE = 'employee'
    ACTOR_MANAGER = 'manager'
    ACTOR_CHOICES = [
        (ACTOR_EMPLOYEE, 'Nhân viên'),
        (ACTOR_MANAGER, 'Quản lý'),
    ]

    ACTION_UPDATE = 'update'
    ACTION_SUBMIT = 'submit'
    ACTION_RESUBMIT = 'resubmit'
    ACTION_CHOICES = [
        (ACTION_UPDATE, 'Chỉnh sửa'),
        (ACTION_SUBMIT, 'Gửi báo cáo'),
        (ACTION_RESUBMIT, 'Cập nhật báo cáo'),
    ]

    report = models.ForeignKey(
        DailyWorkReport,
        on_delete=models.CASCADE,
        related_name='edit_logs',
        verbose_name='Báo cáo',
    )
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='report_edit_logs',
        verbose_name='Người sửa',
    )
    actor_kind = models.CharField(
        max_length=20,
        choices=ACTOR_CHOICES,
        verbose_name='Vai trò',
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        default=ACTION_UPDATE,
        verbose_name='Thao tác',
    )
    summary = models.CharField(max_length=500, blank=True, verbose_name='Mô tả')
    detail = models.TextField(blank=True, verbose_name='Chi tiết thay đổi')
    edited_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Thời gian')

    class Meta:
        ordering = ['-edited_at', '-id']
        verbose_name = 'Lịch sử chỉnh sửa báo cáo'
        verbose_name_plural = 'Lịch sử chỉnh sửa báo cáo'
        indexes = [
            models.Index(fields=['report', '-edited_at']),
        ]

    def __str__(self):
        return f'{self.report_id} — {self.get_actor_kind_display()} — {self.edited_at}'

    @property
    def editor_name(self):
        if not self.edited_by_id:
            return '—'
        profile = getattr(self.edited_by, 'profile', None)
        if profile and profile.full_name:
            return profile.full_name
        return self.edited_by.get_username()


class ProductionReportReminderLog(models.Model):
    """Đã gửi push nhắc nộp báo cáo SX — tránh gửi trùng theo ca/đợt."""

    WAVE_1 = 1
    WAVE_2 = 2
    WAVE_CHOICES = (
        (WAVE_1, 'Đợt 1'),
        (WAVE_2, 'Đợt 2'),
    )

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='production_report_reminder_logs',
        verbose_name='Nhân viên',
    )
    report_date = models.DateField(verbose_name='Ngày báo cáo')
    shift = models.CharField(max_length=20, choices=DailyWorkReport.SHIFT_CHOICES, verbose_name='Ca')
    wave = models.PositiveSmallIntegerField(choices=WAVE_CHOICES, verbose_name='Đợt nhắc')
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'report_date', 'shift', 'wave'],
                name='uniq_prod_report_reminder_employee_date_shift_wave',
            ),
        ]
        ordering = ['-sent_at']
        verbose_name = 'Log nhắc nộp báo cáo SX'
        verbose_name_plural = 'Log nhắc nộp báo cáo SX'

    def __str__(self):
        return f'{self.employee} · {self.report_date} · {self.shift} · đợt {self.wave}'


class ReportsGeneralSettings(models.Model):
    """Singleton (pk=1) — thiết lập chung module Báo cáo SX."""

    workers_may_edit_stage_time = models.BooleanField(
        default=True,
        verbose_name='Công nhân được sửa thời gian công đoạn',
    )
    managers_may_edit_stage_time = models.BooleanField(
        default=True,
        verbose_name='Quản lý được sửa thời gian công đoạn',
    )
    allow_edit_wrong_stage_time = models.BooleanField(
        default=True,
        verbose_name='Báo cáo sai: cho sửa thời gian công đoạn sai',
        help_text='Khi bật — vẫn sửa được giờ công đoạn sai dù đã tắt quyền sửa giờ thường.',
    )
    auto_submit_time = models.TimeField(
        default=time(23, 30),
        verbose_name='Giờ tự động nộp ca sáng',
        help_text='Giờ local trên VPS — cron chạy mỗi 5 phút trong cửa sổ grace.',
    )
    night_auto_submit_enabled = models.BooleanField(
        default=True,
        verbose_name='Bật tự động nộp ca tối',
    )
    night_auto_submit_time = models.TimeField(
        default=time(5, 0),
        verbose_name='Giờ tự động nộp ca tối',
        help_text='Thường sau khi ca tối kết thúc (~5h). Ngày BC = ngày bắt đầu 17h hôm trước.',
    )
    night_default_declared_work_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('9.50'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('23.99'))],
        verbose_name='Giờ làm việc mặc định ca tối',
    )
    approve_deadline_hours = models.PositiveSmallIntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
        verbose_name='Thời hạn duyệt (giờ)',
        help_text='Sau khi nộp — hạn SLA duyệt (badge quá hạn). Quản lý vẫn duyệt được đến hạn không duyệt.',
    )
    unapprove_deadline_days = models.PositiveSmallIntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        verbose_name='Thời hạn hoàn duyệt (ngày)',
        help_text='Số ngày sau khi duyệt mà quản lý còn được hoàn duyệt.',
    )
    auto_reject_deadline_hours = models.PositiveSmallIntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
        verbose_name='Thời hạn không duyệt (giờ)',
        help_text='Sau khi nộp — quá hạn tự chuyển «Không duyệt».',
    )
    employee_edit_deadline_hours = models.PositiveSmallIntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
        verbose_name='Thời hạn CN sửa sau nộp (giờ)',
    )
    default_declared_work_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('9.50'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('23.99'))],
        verbose_name='Giờ làm việc mặc định khi tự nộp',
    )
    work_hours_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('7.50'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('23.99'))],
        verbose_name='Giờ làm việc tối thiểu',
    )
    work_hours_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('16.00'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('24.00'))],
        verbose_name='Giờ làm việc tối đa (không gồm)',
    )
    auto_approve_proxy_reports = models.BooleanField(
        default=True,
        verbose_name='Tự duyệt báo cáo nhập hộ toàn bộ',
    )
    auto_approve_manager_edited_reports = models.BooleanField(
        default=True,
        verbose_name='Tự duyệt khi quản lý sửa báo cáo đã nộp',
        help_text='Quản lý / tổ trưởng sửa, thêm, xóa công đoạn hoặc thời gian làm việc — báo cáo chuyển sang Đã duyệt.',
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Cập nhật bởi',
    )

    class Meta:
        verbose_name = 'Thiết lập chung báo cáo'
        verbose_name_plural = 'Thiết lập chung báo cáo'

    def __str__(self):
        return 'Thiết lập chung báo cáo'

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if (
            self.auto_reject_deadline_hours is not None
            and self.approve_deadline_hours is not None
            and self.auto_reject_deadline_hours < self.approve_deadline_hours
        ):
            errors['auto_reject_deadline_hours'] = (
                'Thời hạn không duyệt phải lớn hơn hoặc bằng thời hạn duyệt.'
            )
        if (
            self.work_hours_min is not None
            and self.work_hours_max is not None
            and self.work_hours_min >= self.work_hours_max
        ):
            errors['work_hours_max'] = 'Giờ tối đa phải lớn hơn giờ tối thiểu.'
        if (
            self.default_declared_work_hours is not None
            and self.work_hours_min is not None
            and self.work_hours_max is not None
            and (
                self.default_declared_work_hours < self.work_hours_min
                or self.default_declared_work_hours >= self.work_hours_max
            )
        ):
            errors['default_declared_work_hours'] = (
                'Giờ mặc định phải nằm trong khoảng giờ hợp lệ.'
            )
        if (
            self.night_default_declared_work_hours is not None
            and self.work_hours_min is not None
            and self.work_hours_max is not None
            and (
                self.night_default_declared_work_hours < self.work_hours_min
                or self.night_default_declared_work_hours >= self.work_hours_max
            )
        ):
            errors['night_default_declared_work_hours'] = (
                'Giờ mặc định ca tối phải nằm trong khoảng giờ hợp lệ.'
            )
        if errors:
            raise ValidationError(errors)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

