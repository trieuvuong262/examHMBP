"""Tuyển dụng — vị trí, ứng viên, hồ sơ đính kèm, đánh giá của quản lý, phỏng vấn, lịch sử.

HỒ SƠ ỨNG VIÊN (CV) LÀ DỮ LIỆU CÁ NHÂN
--------------------------------------
* File lưu ở ``MEDIA_ROOT/_private/recruitment/`` với tên UUID, **không** có URL
  public; nginx chặn ``/media/_private/``.
* Chỉ phục vụ qua view ``recruitment_file`` (kiểm tra quyền xem ứng viên).
"""

import os
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from hrm.choices import GENDER_CHOICES, POSITION_CHOICES

# Đuôi được nhận làm hồ sơ ứng viên → content-type khi trả file.
CANDIDATE_FILE_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
PREVIEW_PDF = frozenset({'.pdf'})
PREVIEW_IMAGE = frozenset({'.jpg', '.jpeg', '.png'})


class PrivateCandidateStorage(FileSystemStorage):
    """Không sinh URL — mọi lượt xem phải đi qua view ``recruitment_file`` có kiểm tra quyền."""

    def url(self, name):
        raise ValueError('Hồ sơ ứng viên không có URL công khai — dùng view recruitment_file.')


def candidate_file_storage():
    return PrivateCandidateStorage(location=os.path.join(settings.MEDIA_ROOT, '_private', 'recruitment'))


def candidate_file_upload_to(instance, filename):
    ext = os.path.splitext(filename or '')[1].lower()
    if ext not in CANDIDATE_FILE_TYPES:
        ext = '.bin'
    return f'cv/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}{ext}'


class RecruitmentOption(models.Model):
    """Danh mục thiết lập (menu Tuyển dụng → Thiết lập)."""

    name = models.CharField(max_length=120, verbose_name='Tên')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')

    class Meta:
        abstract = True
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class InterviewLocation(RecruitmentOption):
    note = models.CharField(max_length=255, blank=True, verbose_name='Địa chỉ / ghi chú')

    class Meta(RecruitmentOption.Meta):
        verbose_name = 'Địa điểm họp'
        verbose_name_plural = 'Địa điểm họp'
        constraints = [models.UniqueConstraint(fields=['name'], name='uniq_interview_location_name')]


class CandidateSource(RecruitmentOption):
    """Mã ``code`` lưu vào ``Candidate.source`` — đổi tên không ảnh hưởng hồ sơ cũ."""

    code = models.SlugField(max_length=20, unique=True, verbose_name='Mã')
    is_system = models.BooleanField(default=False, verbose_name='Hệ thống')

    class Meta(RecruitmentOption.Meta):
        verbose_name = 'Nguồn hồ sơ'
        verbose_name_plural = 'Nguồn hồ sơ'


class CandidateFileKind(RecruitmentOption):
    """Mã ``code`` lưu vào ``CandidateFile.kind``; ``is_cv`` = dùng cho nút «Xem CV»."""

    code = models.SlugField(max_length=20, unique=True, verbose_name='Mã')
    is_cv = models.BooleanField(default=False, verbose_name='Là CV')
    is_system = models.BooleanField(default=False, verbose_name='Hệ thống')

    class Meta(RecruitmentOption.Meta):
        verbose_name = 'Loại hồ sơ'
        verbose_name_plural = 'Loại hồ sơ'


_OPTIONS_CACHE_KEY = 'recruitment:option-labels'
_OPTIONS_CACHE_TTL = 30  # giây — cache có thể là locmem riêng từng worker


def _option_labels() -> dict:
    data = cache.get(_OPTIONS_CACHE_KEY)
    if data is None:
        data = {
            'sources': dict(CandidateSource.objects.values_list('code', 'name')),
            'kinds': dict(CandidateFileKind.objects.values_list('code', 'name')),
            'cv': set(CandidateFileKind.objects.filter(is_cv=True).values_list('code', flat=True)),
        }
        cache.set(_OPTIONS_CACHE_KEY, data, _OPTIONS_CACHE_TTL)
    return data


def clear_option_cache():
    cache.delete(_OPTIONS_CACHE_KEY)


def source_labels() -> dict:
    return _option_labels()['sources']


def file_kind_labels() -> dict:
    return _option_labels()['kinds']


def cv_kind_codes() -> set:
    return _option_labels()['cv']


class JobPosting(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_OPEN = 'open'
    STATUS_PAUSED = 'paused'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_OPEN, 'Đang tuyển'),
        (STATUS_PAUSED, 'Tạm dừng'),
        (STATUS_CLOSED, 'Đã đóng'),
    ]

    POSITION_CHOICES = POSITION_CHOICES
    title = models.CharField(max_length=255, verbose_name='Tiêu đề tuyển dụng')
    target_department = models.ForeignKey(
        'hrm.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_postings',
        verbose_name='Phòng ban',
    )
    # Bộ phận cần người — để trống = cả phòng ban (chỉ Trưởng phòng / Giám đốc phụ trách).
    target_division = models.ForeignKey(
        'hrm.Division',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_postings',
        verbose_name='Bộ phận',
    )
    # Nhãn phòng ban cũ (text tự do) — giữ để hiển thị dữ liệu trước khi có FK.
    department = models.CharField(max_length=100, blank=True, verbose_name='Phòng ban (cũ)')
    position = models.CharField(max_length=50, choices=POSITION_CHOICES, verbose_name='Chức danh')
    quantity = models.PositiveIntegerField(default=1, verbose_name='Số lượng cần tuyển')
    salary_min = models.PositiveIntegerField(null=True, blank=True, verbose_name='Lương từ (VNĐ/tháng)')
    salary_max = models.PositiveIntegerField(null=True, blank=True, verbose_name='Lương đến (VNĐ/tháng)')
    salary_negotiable = models.BooleanField(default=False, verbose_name='Lương thỏa thuận')
    description = models.TextField(blank=True, verbose_name='Mô tả công việc')
    requirements = models.TextField(blank=True, verbose_name='Yêu cầu ứng viên')
    deadline = models.DateField(null=True, blank=True, verbose_name='Hạn nộp hồ sơ')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
        verbose_name='Trạng thái',
    )
    service_request = models.OneToOneField(
        'service_requests.ServiceRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_posting',
        verbose_name='Đề xuất tuyển dụng',
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='job_postings_created', verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='Ngày đóng')

    class Meta:
        verbose_name = 'Vị trí tuyển dụng'
        verbose_name_plural = 'Vị trí tuyển dụng'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.department_label})'

    @property
    def department_label(self) -> str:
        if self.target_department_id:
            label = self.target_department.name
            if self.target_division_id:
                label = f'{label} · {self.target_division.name}'
            return label
        return self.department or '—'

    @property
    def salary_label(self) -> str:
        """VD: «8.000.000 – 12.000.000 đ», «Từ 8.000.000 đ», «Thỏa thuận»; rỗng nếu chưa nhập."""
        def vnd(n):
            return f'{n:,}'.replace(',', '.')

        lo, hi = self.salary_min, self.salary_max
        if lo and hi:
            text = f'{vnd(lo)} đ' if lo == hi else f'{vnd(lo)} – {vnd(hi)} đ'
        elif lo:
            text = f'Từ {vnd(lo)} đ'
        elif hi:
            text = f'Đến {vnd(hi)} đ'
        else:
            return 'Thỏa thuận' if self.salary_negotiable else ''
        return f'{text} (thỏa thuận)' if self.salary_negotiable else text

    @property
    def is_expired(self) -> bool:
        return bool(self.deadline and timezone.localdate() > self.deadline)

    @property
    def accepts_candidates(self) -> bool:
        return self.status == self.STATUS_OPEN and not self.is_expired


class Candidate(models.Model):
    STATUS_NEW = 'new'
    STATUS_REVIEWING = 'reviewing'
    STATUS_INTERVIEWING = 'interviewing'
    STATUS_OFFERED = 'offered'
    STATUS_HIRED = 'hired'
    STATUS_NOT_ONBOARDED = 'not_onboarded'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_NEW, 'Mới'),
        (STATUS_REVIEWING, 'Chờ quản lý đánh giá'),
        (STATUS_INTERVIEWING, 'Phỏng vấn'),
        (STATUS_OFFERED, 'Trúng tuyển'),
        (STATUS_HIRED, 'Đã nhận việc'),
        (STATUS_NOT_ONBOARDED, 'Không nhận việc'),
        (STATUS_REJECTED, 'Loại'),
    ]

    # Mã nguồn có sẵn — danh mục đầy đủ ở CandidateSource (Thiết lập).
    SOURCE_HR = 'hr'
    SOURCE_REFERRAL = 'referral'
    SOURCE_WALK_IN = 'walk_in'
    SOURCE_ONLINE = 'online'

    job_posting = models.ForeignKey(
        JobPosting, on_delete=models.PROTECT, related_name='candidates',
        verbose_name='Ứng tuyển vị trí',
    )
    full_name = models.CharField(max_length=255, verbose_name='Họ và tên')
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, verbose_name='Giới tính')
    date_of_birth = models.DateField(null=True, blank=True, verbose_name='Ngày sinh')
    email = models.EmailField(blank=True, verbose_name='Email')
    phone = models.CharField(max_length=20, verbose_name='Số điện thoại')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True,
        verbose_name='Trạng thái',
    )
    source = models.CharField(max_length=20, default=SOURCE_HR, verbose_name='Nguồn hồ sơ')
    referred_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='referred_candidates', verbose_name='Người đề xuất',
    )
    reject_reason = models.TextField(blank=True, verbose_name='Lý do loại / không nhận việc')
    status_changed_at = models.DateTimeField(null=True, blank=True, verbose_name='Đổi trạng thái lúc')
    employee = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recruitment_candidate', verbose_name='Tài khoản nhân viên',
    )
    applied_at = models.DateTimeField(auto_now_add=True, verbose_name='Ngày nộp')

    class Meta:
        verbose_name = 'Ứng viên'
        verbose_name_plural = 'Ứng viên'
        ordering = ['-applied_at']

    def __str__(self):
        return f'{self.full_name} - {self.job_posting.title}'

    @property
    def interview_or_none(self):
        try:
            return self.interview
        except Interview.DoesNotExist:
            return None

    @property
    def source_label(self):
        return source_labels().get(self.source, self.source)

    @property
    def primary_file(self):
        """CV mới nhất (ưu tiên loại «Là CV») — dùng cho nút «Xem CV»."""
        files = list(self.files.all())  # tận dụng prefetch_related('files')
        if not files:
            return None
        cv_codes = cv_kind_codes()
        cvs = [f for f in files if f.kind in cv_codes]
        return max(cvs or files, key=lambda f: (f.uploaded_at, f.pk))


class CandidateFile(models.Model):
    # Mã loại có sẵn — danh mục đầy đủ ở CandidateFileKind (Thiết lập).
    KIND_CV = 'cv'
    KIND_OTHER = 'other'

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name='files', verbose_name='Ứng viên',
    )
    kind = models.CharField(max_length=20, default=KIND_CV, verbose_name='Loại')
    file = models.FileField(
        storage=candidate_file_storage, upload_to=candidate_file_upload_to, max_length=255, verbose_name='File',
    )
    original_name = models.CharField(max_length=255, verbose_name='Tên file gốc')
    size = models.PositiveBigIntegerField(default=0, verbose_name='Dung lượng')
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='candidate_files_uploaded', verbose_name='Người tải lên',
    )
    uploaded_at = models.DateTimeField(default=timezone.now, verbose_name='Tải lên lúc')

    class Meta:
        verbose_name = 'Hồ sơ đính kèm'
        verbose_name_plural = 'Hồ sơ đính kèm'
        ordering = ['-uploaded_at', '-id']

    def __str__(self):
        return self.original_name

    @property
    def kind_label(self):
        return file_kind_labels().get(self.kind, self.kind)

    @property
    def ext(self) -> str:
        return os.path.splitext(self.file.name or '')[1].lower()

    @property
    def content_type(self) -> str:
        return CANDIDATE_FILE_TYPES.get(self.ext, 'application/octet-stream')

    @property
    def preview_kind(self) -> str:
        if self.ext in PREVIEW_PDF:
            return 'pdf'
        if self.ext in PREVIEW_IMAGE:
            return 'image'
        return 'download'

    @property
    def icon(self) -> str:
        return {
            'pdf': 'bi-file-earmark-pdf',
            'image': 'bi-file-earmark-image',
        }.get(self.preview_kind, 'bi-file-earmark-word')


@receiver(post_delete, sender=CandidateFile)
def _delete_candidate_file_blob(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


@receiver([post_save, post_delete], sender=CandidateSource)
@receiver([post_save, post_delete], sender=CandidateFileKind)
def _reset_option_cache(sender, **kwargs):
    clear_option_cache()


class CandidateReview(models.Model):
    """Đánh giá hồ sơ của Trưởng bộ phận / Trưởng phòng / Giám đốc."""

    DECISION_RECOMMEND = 'recommend'
    DECISION_CONSIDER = 'consider'
    DECISION_NOT_SUITABLE = 'not_suitable'
    DECISION_CHOICES = [
        (DECISION_RECOMMEND, 'Đạt'),
        (DECISION_CONSIDER, 'Cân nhắc'),
        (DECISION_NOT_SUITABLE, 'Không đạt'),
    ]
    # «Cân nhắc» chỉ còn để hiển thị đánh giá cũ — quản lý chỉ chọn Đạt / Không đạt.
    ACTIVE_DECISIONS = (DECISION_RECOMMEND, DECISION_NOT_SUITABLE)

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name='reviews', verbose_name='Ứng viên',
    )
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='candidate_reviews',
        verbose_name='Người đánh giá',
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, verbose_name='Kết luận')
    rating = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Điểm hồ sơ (1–5)')
    comment = models.TextField(blank=True, verbose_name='Nhận xét')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Đánh giá ứng viên'
        verbose_name_plural = 'Đánh giá ứng viên'
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['candidate', 'reviewer'], name='uniq_candidate_reviewer'),
        ]

    def __str__(self):
        return f'{self.candidate.full_name} — {self.get_decision_display()}'


class Interview(models.Model):
    RESULT_PENDING = 'pending'
    RESULT_PASS = 'pass'
    RESULT_FAIL = 'fail'
    RESULT_CHOICES = [
        (RESULT_PENDING, 'Chưa có kết quả'),
        (RESULT_PASS, 'Đạt'),
        (RESULT_FAIL, 'Không đạt'),
    ]

    candidate = models.OneToOneField(
        Candidate, on_delete=models.CASCADE, related_name='interview', verbose_name='Ứng viên',
    )
    interview_time = models.DateTimeField(verbose_name='Bắt đầu')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='Kết thúc')
    location = models.CharField(max_length=255, blank=True, verbose_name='Địa điểm')
    interviewers = models.ManyToManyField(
        User, related_name='interviews_assigned', blank=True, verbose_name='Người phỏng vấn',
    )
    result = models.CharField(
        max_length=10, choices=RESULT_CHOICES, default=RESULT_PENDING, verbose_name='Kết quả',
    )
    result_notes = models.TextField(blank=True, verbose_name='Nhận xét phỏng vấn')

    class Meta:
        verbose_name = 'Lịch phỏng vấn'
        verbose_name_plural = 'Lịch phỏng vấn'
        ordering = ['interview_time']

    def __str__(self):
        return f'Phỏng vấn: {self.candidate.full_name}'

    @property
    def duration_minutes(self) -> int | None:
        if not self.end_time:
            return None
        return int((self.end_time - self.interview_time).total_seconds() // 60)

    @property
    def duration_label(self) -> str:
        return format_duration(self.duration_minutes)

    @property
    def time_range_label(self) -> str:
        """«08:00 – 09:30 07/10/2026» theo giờ địa phương."""
        start = timezone.localtime(self.interview_time)
        if not self.end_time:
            return f'{start:%H:%M %d/%m/%Y}'
        end = timezone.localtime(self.end_time)
        if end.date() == start.date():
            return f'{start:%H:%M} – {end:%H:%M} {start:%d/%m/%Y}'
        return f'{start:%H:%M %d/%m/%Y} – {end:%H:%M %d/%m/%Y}'


def format_duration(minutes) -> str:
    if not minutes:
        return ''
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f'{hours} giờ {mins} phút'
    return f'{hours} giờ' if hours else f'{mins} phút'


class CandidateEvent(models.Model):
    """Lịch sử thao tác trên hồ sơ ứng viên (không sửa / xóa)."""

    KIND_CREATED = 'created'
    KIND_STATUS = 'status'
    KIND_NOTE = 'note'
    KIND_REVIEW = 'review'
    KIND_INTERVIEW = 'interview'
    KIND_ONBOARD = 'onboard'
    KIND_FILE = 'file'
    KIND_CHOICES = [
        (KIND_CREATED, 'Tạo hồ sơ'),
        (KIND_STATUS, 'Đổi trạng thái'),
        (KIND_NOTE, 'Ghi chú'),
        (KIND_REVIEW, 'Đánh giá hồ sơ'),
        (KIND_INTERVIEW, 'Phỏng vấn'),
        (KIND_ONBOARD, 'Onboard'),
        (KIND_FILE, 'Hồ sơ đính kèm'),
    ]

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name='events', verbose_name='Ứng viên',
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name='Loại')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    message = models.TextField(blank=True, verbose_name='Nội dung')
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='candidate_events', verbose_name='Người thực hiện',
    )
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Thời gian')

    class Meta:
        verbose_name = 'Lịch sử ứng viên'
        verbose_name_plural = 'Lịch sử ứng viên'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.candidate_id} · {self.get_kind_display()}'

    @property
    def from_status_label(self) -> str:
        return dict(Candidate.STATUS_CHOICES).get(self.from_status, self.from_status)

    @property
    def to_status_label(self) -> str:
        return dict(Candidate.STATUS_CHOICES).get(self.to_status, self.to_status)
