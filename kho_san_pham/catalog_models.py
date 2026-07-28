"""Danh mục loại mã + Style + map nhóm hàng KV → loại."""

from django.conf import settings
from django.db import models

from kho_san_pham.choices import (
    DEFAULT_BRAND,
    KV_MAP_MATCH_CHOICES,
    KV_MAP_MATCH_EXACT,
    STYLE_SOURCE_CHOICES,
    STYLE_SOURCE_MANUAL,
)


class ProductType(models.Model):
    """Loại mã chuẩn hóa (TEE, SET-SC, ACC-BALO, …)."""

    code = models.CharField(max_length=32, unique=True, verbose_name='Mã loại')
    name = models.CharField(max_length=120, verbose_name='Nội dung')
    sort_order = models.PositiveSmallIntegerField(default=100, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'kho_sp_product_type'
        ordering = ['sort_order', 'code']
        verbose_name = 'Loại sản phẩm (mã)'
        verbose_name_plural = 'Loại sản phẩm (mã)'

    def __str__(self):
        return f'{self.code} — {self.name}'

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        self.name = (self.name or '').strip()
        super().save(*args, **kwargs)


class ProductStyle(models.Model):
    """Mã Style = JP-{LOẠI}-{NHÓM?}-{hậu tố}.

    Ví dụ: ``JP-TEE-00-260001`` (tay), ``JP-JKT-00-SP007105`` (KV), ``JP-SET-SC-SP002771`` (loại đã có nhóm).
    """

    code = models.CharField(max_length=80, unique=True, verbose_name='Mã Style')
    product_type = models.ForeignKey(
        ProductType,
        on_delete=models.PROTECT,
        related_name='styles',
        verbose_name='Loại',
    )
    name = models.CharField(max_length=500, blank=True, default='', verbose_name='Tên / mô tả')
    brand = models.CharField(max_length=16, default=DEFAULT_BRAND, verbose_name='Brand')
    year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Năm')
    sequence = models.PositiveIntegerField(null=True, blank=True, verbose_name='STT')
    root_kiotviet_code = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        verbose_name='Mã KV gốc',
    )
    source = models.CharField(
        max_length=20,
        choices=STYLE_SOURCE_CHOICES,
        default=STYLE_SOURCE_MANUAL,
        verbose_name='Nguồn',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kho_sp_styles_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kho_sp_product_style'
        ordering = ['code']
        verbose_name = 'Style'
        verbose_name_plural = 'Style'
        indexes = [
            models.Index(fields=['product_type', 'year']),
            models.Index(fields=['source', 'is_active']),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        self.brand = (self.brand or DEFAULT_BRAND).strip().upper() or DEFAULT_BRAND
        self.name = (self.name or '').strip()
        self.root_kiotviet_code = (self.root_kiotviet_code or '').strip()
        super().save(*args, **kwargs)


class ProductTypeKvMap(models.Model):
    """Gán nhóm hàng KiotViet → loại mã (để sync sinh Style)."""

    match_value = models.CharField(max_length=255, verbose_name='Nhóm hàng KV')
    match_mode = models.CharField(
        max_length=20,
        choices=KV_MAP_MATCH_CHOICES,
        default=KV_MAP_MATCH_EXACT,
        verbose_name='Kiểu khớp',
    )
    product_type = models.ForeignKey(
        ProductType,
        on_delete=models.CASCADE,
        related_name='kv_maps',
        verbose_name='Loại mã',
    )
    priority = models.PositiveSmallIntegerField(
        default=100,
        help_text='Số nhỏ = ưu tiên cao hơn.',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'kho_sp_product_type_kv_map'
        ordering = ['priority', 'match_value']
        verbose_name = 'Map nhóm hàng KV → loại'
        verbose_name_plural = 'Map nhóm hàng KV → loại'
        constraints = [
            models.UniqueConstraint(
                fields=['match_value', 'match_mode'],
                name='kho_sp_type_kv_map_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.match_value} → {self.product_type_id}'

    def save(self, *args, **kwargs):
        self.match_value = (self.match_value or '').strip()
        self.notes = (self.notes or '').strip()
        super().save(*args, **kwargs)
