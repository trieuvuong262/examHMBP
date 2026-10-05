from django.conf import settings
from django.db import models


class TienDoItem(models.Model):
    """Một dòng tiến độ release chức năng trên Portal hoặc Website sỉ/lẻ."""

    PLATFORM_PORTAL = 'portal'
    PLATFORM_WHOLESALE_RETAIL = 'wholesale_retail'
    PLATFORM_CHOICES = [
        (PLATFORM_PORTAL, 'Tiến độ Portal'),
        (PLATFORM_WHOLESALE_RETAIL, 'Tiến độ Website sỉ/lẻ'),
    ]

    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        db_index=True,
        verbose_name='Nền tảng',
    )
    feature = models.CharField(max_length=255, blank=True, verbose_name='Tính năng')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    user_flow = models.TextField(blank=True, verbose_name='User flow')
    feedback = models.TextField(blank=True, verbose_name='Feedback')
    note = models.TextField(blank=True, verbose_name='Ghi chú')
    is_tested = models.BooleanField(default=False, verbose_name='Đã test')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tien_do_items_created',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Tên cột IT nhập / người test nhập — dùng để phân quyền chỉnh sửa inline.
    IT_COLUMNS = ('feature', 'description', 'user_flow')
    TESTER_COLUMNS = ('feedback', 'note')
    EDITABLE_COLUMNS = IT_COLUMNS + TESTER_COLUMNS

    # Cột cho phép nội dung rich (text + ảnh inline). 'feature' là CharField nên để text thuần.
    RICH_COLUMNS = ('description', 'user_flow', 'feedback', 'note')

    COLUMN_LABELS = {
        'feature': 'Tính năng',
        'description': 'Mô tả',
        'user_flow': 'User flow',
        'feedback': 'Feedback',
        'note': 'Ghi chú',
    }

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Dòng tiến độ'
        verbose_name_plural = 'Dòng tiến độ'

    def __str__(self):
        return f'[{self.get_platform_display()}] {self.feature or "(chưa đặt tên)"}'
