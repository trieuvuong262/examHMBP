"""Mô hình 3D dạng file HTML tự chứa (Three.js...) — upload và xem trong portal.

BẢO MẬT
-------
File HTML do người dùng upload chạy được JavaScript. Nếu phục vụ cùng origin với
portal thì là stored XSS (đọc cookie/CSRF, gọi API thay người xem). Vì vậy:

* File lưu ở ``MEDIA_ROOT/_private/xay_dung/`` với tên UUID, **không** có URL
  public; nginx chặn ``/media/_private/``.
* Chỉ phục vụ qua view ``xay_dung:raw`` (kiểm tra quyền) kèm header
  ``Content-Security-Policy: sandbox allow-scripts`` (không ``allow-same-origin``)
  → trang chạy trong origin "null", không đụng được session portal.
"""

import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models


def private_storage():
    """Storage riêng, không có base_url — file không bao giờ có link /media/ trực tiếp."""
    return FileSystemStorage(
        location=os.path.join(settings.MEDIA_ROOT, '_private', 'xay_dung'),
        base_url=None,
    )


def model_upload_to(instance, filename):
    ext = os.path.splitext(filename or '')[1].lower()
    if ext not in ('.html', '.htm'):
        ext = '.html'
    return f'{uuid.uuid4().hex}{ext}'


class Model3D(models.Model):
    title = models.CharField('Tiêu đề', max_length=255)
    description = models.TextField('Mô tả', blank=True)
    html_file = models.FileField(
        'File HTML',
        storage=private_storage,
        upload_to=model_upload_to,
        max_length=255,
    )
    original_name = models.CharField('Tên file gốc', max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField('Dung lượng', default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='xay_dung_models',
        verbose_name='Người tải lên',
    )
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Cập nhật', auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Mô hình 3D'
        verbose_name_plural = 'Mô hình 3D'

    def __str__(self):
        return self.title

    def uploader_display(self):
        user = self.uploaded_by
        if not user:
            return '—'
        return user.get_full_name() or user.username
