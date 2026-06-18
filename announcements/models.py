import os

from django.conf import settings
from django.db import models
from django.urls import reverse
from ckeditor.fields import RichTextField

from .nas_storage import (
    AnnouncementNasStorage,
    announcement_file_upload_to,
    is_legacy_announcement_path,
)


class Announcement(models.Model):
    TYPE_TEXT = 'TEXT'
    TYPE_PDF = 'PDF'
    TYPE_VIDEO = 'VIDEO'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Văn bản'),
        (TYPE_PDF, 'PDF'),
        (TYPE_VIDEO, 'Video'),
    ]

    title = models.CharField(max_length=255, verbose_name='Tiêu đề')
    summary = models.CharField(max_length=500, blank=True, verbose_name='Tóm tắt')
    content_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default=TYPE_TEXT,
        verbose_name='Loại nội dung',
    )
    body = RichTextField(blank=True, verbose_name='Nội dung văn bản')
    pdf_file = models.FileField(
        upload_to=announcement_file_upload_to,
        storage=AnnouncementNasStorage(),
        blank=True,
        null=True,
        verbose_name='File PDF',
    )
    video_file = models.FileField(
        upload_to=announcement_file_upload_to,
        storage=AnnouncementNasStorage(),
        blank=True,
        null=True,
        verbose_name='File video',
    )
    original_file = models.FileField(
        upload_to=announcement_file_upload_to,
        storage=AnnouncementNasStorage(),
        blank=True,
        null=True,
        verbose_name='File gốc đính kèm',
    )
    is_active = models.BooleanField(default=True, verbose_name='Đang hiển thị')
    is_pinned = models.BooleanField(default=False, verbose_name='Ghim lên đầu')
    require_acknowledgment = models.BooleanField(
        default=True,
        verbose_name='Yêu cầu xác nhận đã đọc',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='announcements_created',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        verbose_name = 'Thông báo'
        verbose_name_plural = 'Thông báo'

    def __str__(self):
        return self.title

    def file_display_name(self, field_name: str) -> str:
        field = getattr(self, field_name, None)
        if not field or not field.name:
            return ''
        return os.path.basename(field.name)

    def file_url(self, field_name: str) -> str:
        field = getattr(self, field_name, None)
        if not field or not field.name:
            return ''
        if is_legacy_announcement_path(field.name):
            return field.url
        return reverse('announcements:file', kwargs={'pk': self.pk, 'field': field_name})

    @property
    def pdf_file_url(self) -> str:
        return self.file_url('pdf_file')

    @property
    def video_file_url(self) -> str:
        return self.file_url('video_file')

    @property
    def original_file_url(self) -> str:
        return self.file_url('original_file')

    @property
    def original_file_display_name(self) -> str:
        return self.file_display_name('original_file')


class AnnouncementRead(models.Model):
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name='reads',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='announcement_reads',
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('announcement', 'user')
        verbose_name = 'Xác nhận đọc'
        verbose_name_plural = 'Xác nhận đọc'

    def __str__(self):
        return f'{self.user} - {self.announcement}'
