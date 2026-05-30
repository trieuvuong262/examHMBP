from django.conf import settings
from django.db import models


class UserNote(models.Model):
    COLOR_CHOICES = (
        ('yellow', 'Vàng'),
        ('blue', 'Xanh dương'),
        ('green', 'Xanh lá'),
        ('pink', 'Hồng'),
        ('gray', 'Xám'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tool_notes',
        verbose_name='Người dùng',
    )
    title = models.CharField(max_length=120, blank=True, verbose_name='Tiêu đề')
    content = models.TextField(blank=True, verbose_name='Nội dung')
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default='yellow', verbose_name='Màu')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Cập nhật')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Tạo lúc')

    class Meta:
        ordering = ['sort_order', '-updated_at']
        verbose_name = 'Ghi chú'
        verbose_name_plural = 'Ghi chú'

    def __str__(self):
        return self.title or f'Ghi chú #{self.pk}'
