from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from kho_san_pham.choices import (
    PRODUCT_TYPE_CHOICES,
    PRODUCT_TYPE_HANG_HOA,
    PRODUCT_TYPE_THANH_PHAM,
    SYNC_SOURCE_CHOICES,
    SYNC_SOURCE_MANUAL,
)
from kho_san_pham.sku_vocabulary import GENDER_CHOICES, GENDER_NONE


class Product(models.Model):
    """Danh mục kho sản phẩm — 1 dòng = 1 SKU (Style–Màu–Size), như hồ sơ thiết kế.

    ``code`` = SKU ghép: ``{style}-{color}-{size}`` (vd. JP-TEE-260001-NVY-M).
    """

    product_type = models.CharField(
        max_length=20,
        choices=PRODUCT_TYPE_CHOICES,
        default=PRODUCT_TYPE_HANG_HOA,
        db_index=True,
        verbose_name='Loại',
    )
    # Loại mã chuẩn (TEE / SET-SC / …) — khác trường product_type thanh_pham|hang_hoa
    catalog_type = models.ForeignKey(
        'kho_san_pham.ProductType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='Loại mã',
    )
    # SKU = Style-[Màu-]Size; Style = JP-{LOẠI}-{hậu tố}
    style_code = models.CharField(
        max_length=80,
        blank=True,
        default='',
        db_index=True,
        verbose_name='Style',
        help_text='Mã Style (vd. JP-TEE-260001, JP-SET-SC-SP002771).',
    )
    color_code = models.CharField(max_length=20, blank=True, default='', db_index=True, verbose_name='Mã màu')
    color_label = models.CharField(max_length=80, blank=True, default='', verbose_name='Tên màu')
    size_label = models.CharField(max_length=20, blank=True, default='', db_index=True, verbose_name='Size')
    gender = models.CharField(
        max_length=10,
        blank=True,
        default=GENDER_NONE,
        choices=GENDER_CHOICES,
        verbose_name='Giới tính',
        help_text='Thuộc tính riêng của SKU, tách khỏi size (trước đây viết lồng "XL-NỮ").',
    )
    code = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='SKU',
        help_text='SKU = Style-Màu-Size (vd. JP-TEE-260001-NVY-M).',
    )
    legacy_code = models.CharField(
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        verbose_name='Mã SKU cũ',
        help_text='Mã trước khi sinh lại theo từ vựng chuẩn. Để tra cứu ngược, không dùng làm khóa.',
    )
    sx_sku = models.ForeignKey(
        'san_xuat.SxSku',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kho_sp_products',
        verbose_name='SKU SX',
    )
    accounting_code = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='Mã kế toán',
    )
    kiotviet_code = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        verbose_name='Mã KiotViet',
    )
    kiotviet_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name='ID KiotViet',
    )
    name = models.CharField(max_length=500, verbose_name='Tên sản phẩm')
    full_name = models.CharField(max_length=500, blank=True, default='', verbose_name='Tên đầy đủ')
    bar_code = models.CharField(max_length=64, blank=True, default='', db_index=True, verbose_name='Mã vạch')
    unit = models.CharField(max_length=32, blank=True, default='', verbose_name='Đơn vị tính')
    category_name = models.CharField(max_length=255, blank=True, default='', verbose_name='Nhóm hàng')
    category_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Đường dẫn nhóm')
    description = models.TextField(blank=True, default='', verbose_name='Mô tả')
    base_price = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Giá bán',
    )
    qty_on_hand = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Tồn kho',
        help_text='Bản sao tồn kho xưởng (XUONG-TP). Nguồn sự thật là sổ kho; cột này chỉ để xem trên danh mục.',
    )
    image = models.ImageField(upload_to='kho_sp/products/', blank=True, verbose_name='Hình ảnh')
    image_url = models.URLField(max_length=500, blank=True, default='', verbose_name='URL ảnh KV')
    allows_sale = models.BooleanField(null=True, blank=True, verbose_name='Cho phép bán')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Đang dùng')
    sync_source = models.CharField(
        max_length=20,
        choices=SYNC_SOURCE_CHOICES,
        default=SYNC_SOURCE_MANUAL,
        verbose_name='Nguồn',
    )
    kv_modified_at = models.DateTimeField(null=True, blank=True, verbose_name='KV sửa lúc')
    synced_at = models.DateTimeField(null=True, blank=True, verbose_name='Đồng bộ lúc')
    notes = models.TextField(blank=True, default='', verbose_name='Ghi chú')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kho_sp_products_created',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kho_sp_product'
        ordering = ['style_code', 'color_code', 'size_label', 'code']
        verbose_name = 'Sản phẩm (SKU)'
        verbose_name_plural = 'Sản phẩm (SKU)'
        constraints = []
        indexes = [
            models.Index(fields=['product_type', 'is_active']),
            models.Index(fields=['kiotviet_code']),
            models.Index(fields=['style_code', 'is_active']),
            models.Index(fields=['accounting_code'], name='kho_sp_prod_account_b08923_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['bar_code'],
                condition=~models.Q(bar_code=''),
                name='kho_sp_product_bar_code_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.code} — {self.name}'

    @property
    def is_thanh_pham(self) -> bool:
        return self.product_type == PRODUCT_TYPE_THANH_PHAM

    @property
    def is_hang_hoa(self) -> bool:
        return self.product_type == PRODUCT_TYPE_HANG_HOA

    @property
    def is_kv_synced(self) -> bool:
        return self.sync_source == 'kiotviet' and self.kiotviet_id is not None

    @property
    def display_image_url(self) -> str:
        if self.image:
            return self.image.url
        return (self.image_url or '').strip()

    @property
    def sku_parts_display(self) -> str:
        parts = [p for p in (self.style_code, self.color_code, self.size_label) if p]
        return ' · '.join(parts) if parts else ''

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        self.legacy_code = (self.legacy_code or '').strip().upper()
        self.style_code = (self.style_code or '').strip().upper()
        self.color_code = (self.color_code or '').strip().upper()
        self.color_label = (self.color_label or '').strip()
        self.size_label = (self.size_label or '').strip().upper()
        self.accounting_code = (self.accounting_code or '').strip()
        self.kiotviet_code = (self.kiotviet_code or '').strip()
        self.name = (self.name or '').strip()
        self.full_name = (self.full_name or '').strip()
        self.bar_code = (self.bar_code or '').strip()
        self.unit = (self.unit or '').strip()
        super().save(*args, **kwargs)


# Re-export catalog models so Django registers them with the app.
from kho_san_pham.catalog_models import ProductStyle, ProductType, ProductTypeKvMap  # noqa: E402,F401
from kho_san_pham.stock_models import (  # noqa: E402,F401
    NegativeStockAlert,
    StockBalance,
    StockLedger,
    Warehouse,
)

