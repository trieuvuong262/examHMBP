from django.conf import settings
from django.db import models
from ckeditor.fields import RichTextField


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
        upload_to='announcements/pdf/',
        blank=True,
        null=True,
        verbose_name='File PDF',
    )
    video_file = models.FileField(
        upload_to='announcements/videos/',
        blank=True,
        null=True,
        verbose_name='File video',
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
