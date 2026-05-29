from django.conf import settings
from django.db import models
from django.utils.text import slugify
from ckeditor.fields import RichTextField


class DocumentCategory(models.Model):
    name = models.CharField(max_length=255, verbose_name='Tên nhóm')
    slug = models.SlugField(max_length=120, unique=True, verbose_name='Mã URL')
    description = models.CharField(max_length=500, blank=True, verbose_name='Mô tả ngắn')
    icon = models.CharField(
        max_length=64,
        default='bi-folder2',
        verbose_name='Icon Bootstrap',
        help_text='Ví dụ: bi-people-fill, bi-folder2',
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang hiển thị')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Nhóm tài liệu'
        verbose_name_plural = 'Nhóm tài liệu'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True) or 'nhom'
            slug = base
            n = 1
            while DocumentCategory.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Document(models.Model):
    TYPE_TEXT = 'TEXT'
    TYPE_PDF = 'PDF'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Văn bản'),
        (TYPE_PDF, 'PDF'),
    ]

    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='Nhóm',
    )
    title = models.CharField(max_length=255, verbose_name='Tiêu đề')
    slug = models.SlugField(max_length=120, verbose_name='Mã URL')
    summary = models.CharField(max_length=500, blank=True, verbose_name='Tóm tắt')
    content_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default=TYPE_TEXT,
        verbose_name='Loại nội dung',
    )
    body = RichTextField(blank=True, verbose_name='Nội dung')
    pdf_file = models.FileField(
        upload_to='documents/pdf/',
        blank=True,
        null=True,
        verbose_name='File PDF',
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang hiển thị')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents_created',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__sort_order', 'sort_order', 'title']
        unique_together = ('category', 'slug')
        verbose_name = 'Tài liệu'
        verbose_name_plural = 'Tài liệu'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title, allow_unicode=True) or 'tai-lieu'
            slug = base
            n = 1
            self.slug = slug
        super().save(*args, **kwargs)


class LibraryQAConfig(models.Model):
    """Cấu hình Hỏi đáp AI — một bản ghi duy nhất (pk=1)."""

    GEMINI_MODEL_CHOICES = [
        ('gemini-1.5-pro', 'Gemini 1.5 Pro'),
        ('gemini-2.0-flash', 'Gemini 2.0 Flash'),
        ('gemini-1.5-flash', 'Gemini 1.5 Flash'),
    ]

    gemini_api_key = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Gemini API Key',
        help_text='Lấy tại Google AI Studio. Để trống nếu dùng biến GEMINI_API_KEY trong file .env.',
    )
    gemini_model = models.CharField(
        max_length=64,
        choices=GEMINI_MODEL_CHOICES,
        default='gemini-1.5-pro',
        verbose_name='Model',
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='library_qa_config_updates',
        verbose_name='Người cập nhật',
    )

    class Meta:
        verbose_name = 'Cấu hình Hỏi đáp AI'
        verbose_name_plural = 'Cấu hình Hỏi đáp AI'

    def __str__(self):
        return 'Cấu hình Hỏi đáp AI'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
