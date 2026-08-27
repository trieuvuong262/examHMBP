"""Kho thành phẩm — tồn và sổ kho.

Soi theo ``kho_npl.StockBalance`` / ``kho_npl.StockLedger``: số dư là một dòng
cho mỗi cặp (SKU, kho), sổ kho là bảng chỉ-ghi-thêm mang ``balance_after``.

Thiết kế: docs/integrations/central-product/inventory-schema.md
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from kho_san_pham.choices import (
    DOC_TYPE_CHOICES,
    MOVEMENT_KIND_CHOICES,
    SOURCE_SYSTEM_CHOICES,
    WAREHOUSE_OWNER_CHOICES,
    WAREHOUSE_OWNER_PORTAL,
    WAREHOUSE_OWNER_SALES,
)


class Warehouse(models.Model):
    """Kho thành phẩm ở xưởng, hoặc điểm bán ở VPS bán hàng."""

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã kho')
    name = models.CharField(max_length=120, verbose_name='Tên kho')
    owner_system = models.CharField(
        max_length=20,
        choices=WAREHOUSE_OWNER_CHOICES,
        default=WAREHOUSE_OWNER_PORTAL,
        db_index=True,
        verbose_name='Hệ sở hữu',
        help_text='Hệ nào được ghi phát sinh vào kho này.',
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Đang dùng')
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kho_sp_warehouse'
        ordering = ['owner_system', 'code']
        verbose_name = 'Kho thành phẩm'
        verbose_name_plural = 'Kho thành phẩm'

    def __str__(self):
        return f'{self.code} — {self.name}'

    @property
    def is_portal_owned(self) -> bool:
        return self.owner_system == WAREHOUSE_OWNER_PORTAL

    @property
    def is_sales_owned(self) -> bool:
        return self.owner_system == WAREHOUSE_OWNER_SALES

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        self.name = (self.name or '').strip()
        super().save(*args, **kwargs)


class StockBalance(models.Model):
    """Số dư tồn hiện tại của một SKU tại một kho.

    Không đặt ``MinValueValidator(0)`` như ``kho_npl.StockBalance``: phát sinh
    bán được đẩy về *sau khi* đã bán, hàng đã ra khỏi kệ nên từ chối ghi chỉ làm
    mất dữ liệu thật. Tồn âm được ghi nhận rồi báo động qua
    ``NegativeStockAlert``.
    """

    product = models.ForeignKey(
        'kho_san_pham.Product',
        on_delete=models.PROTECT,
        related_name='stock_balances',
        verbose_name='SKU',
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='balances',
        verbose_name='Kho',
    )
    qty_on_hand = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Tồn',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kho_sp_stock_balance'
        ordering = ['warehouse', 'product']
        verbose_name = 'Tồn thành phẩm'
        verbose_name_plural = 'Tồn thành phẩm'
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'warehouse'],
                name='kho_sp_balance_product_wh_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['warehouse', 'qty_on_hand']),
        ]

    def __str__(self):
        return f'{self.product_id} @ {self.warehouse_id}: {self.qty_on_hand}'


class StockLedger(models.Model):
    """Sổ kho chỉ-ghi-thêm. Tồn là kết quả cộng dồn của bảng này.

    Bốn trường ``source_*`` là khóa chống trùng: bên gửi cấp chúng từ chứng từ
    gốc của nó, nên gửi lại cùng một phát sinh sẽ va ràng buộc duy nhất thay vì
    cộng tồn lần hai.
    """

    product = models.ForeignKey(
        'kho_san_pham.Product',
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        verbose_name='SKU',
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        verbose_name='Kho',
    )
    kind = models.CharField(
        max_length=24,
        choices=MOVEMENT_KIND_CHOICES,
        db_index=True,
        verbose_name='Loại phát sinh',
    )
    qty_delta = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Biến động')
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Tồn sau')
    unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Giá thành',
        help_text='Bắt buộc với nhập thành phẩm. Phát sinh xuất để trống — giá vốn tính từ tồn.',
    )

    source_system = models.CharField(
        max_length=20,
        choices=SOURCE_SYSTEM_CHOICES,
        db_index=True,
        verbose_name='Hệ nguồn',
    )
    source_doc_type = models.CharField(
        max_length=30,
        choices=DOC_TYPE_CHOICES,
        verbose_name='Loại chứng từ',
    )
    source_doc_code = models.CharField(max_length=60, db_index=True, verbose_name='Số chứng từ')
    source_line_no = models.PositiveIntegerField(default=1, verbose_name='Dòng')

    # occurred_at = thời điểm nghiệp vụ do bên gửi cấp; received_at = lúc ghi sổ.
    # Cửa hàng bán 20h, mạng lỗi, phát sinh về 23h: doanh thu dùng occurred_at,
    # truy vết sự cố đồng bộ dùng received_at. Gộp một trường là mất một trong hai.
    occurred_at = models.DateTimeField(db_index=True, verbose_name='Thời điểm phát sinh')
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm ghi sổ')

    # created_by chỉ có với phát sinh nội bộ Portal; actor là định danh người
    # thực hiện ở hệ nguồn (thu ngân ở VPS bán hàng — không có user trong DB này).
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kho_sp_ledger_entries',
        verbose_name='Người thực hiện',
    )
    actor = models.CharField(max_length=150, blank=True, default='', verbose_name='Người thực hiện (hệ nguồn)')
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')

    class Meta:
        db_table = 'kho_sp_stock_ledger'
        ordering = ['-occurred_at', '-id']
        verbose_name = 'Sổ kho thành phẩm'
        verbose_name_plural = 'Sổ kho thành phẩm'
        constraints = [
            models.UniqueConstraint(
                fields=['source_system', 'source_doc_type', 'source_doc_code', 'source_line_no'],
                name='kho_sp_ledger_source_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['product', 'warehouse', 'occurred_at']),
        ]

    def __str__(self):
        return f'{self.source_doc_code}#{self.source_line_no} · {self.kind} · {self.qty_delta}'


class NegativeStockAlert(models.Model):
    """Một phát sinh đã đẩy tồn xuống âm — cần người xử lý.

    Tồn âm là triệu chứng, không phải nguyên nhân: hoặc có phát sinh nhập chưa
    đẩy lên, hoặc bán trùng, hoặc tồn đầu kỳ sai. Chặn ghi là bịt miệng triệu
    chứng và mất luôn dữ liệu để chẩn đoán.
    """

    ledger_entry = models.OneToOneField(
        StockLedger,
        on_delete=models.CASCADE,
        related_name='negative_alert',
        verbose_name='Dòng sổ kho',
    )
    # Lưu mã dạng chữ để cảnh báo còn đọc được cả khi SKU/kho bị đổi mã.
    product_code = models.CharField(max_length=100, db_index=True, verbose_name='SKU')
    warehouse_code = models.CharField(max_length=40, db_index=True, verbose_name='Kho')
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Tồn sau')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Đã xử lý lúc')
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kho_sp_negative_alerts_resolved',
        verbose_name='Người xử lý',
    )
    resolution_note = models.CharField(max_length=255, blank=True, default='', verbose_name='Cách xử lý')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kho_sp_negative_stock_alert'
        ordering = ['-created_at']
        verbose_name = 'Cảnh báo tồn âm'
        verbose_name_plural = 'Cảnh báo tồn âm'
        indexes = [
            models.Index(fields=['resolved_at']),
        ]

    def __str__(self):
        return f'{self.product_code} @ {self.warehouse_code}: {self.balance_after}'

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None


class StockReceipt(models.Model):
    """Phiếu nhập kho thành phẩm (Portal) — quản lý giống phiếu nhập NPL."""

    number = models.CharField(max_length=40, unique=True, verbose_name='Mã phiếu nhập')
    receipt_date = models.DateField(verbose_name='Ngày nhập')
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='stock_receipts',
        verbose_name='Kho nhập',
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Nháp'),
            ('posted', 'Đã nhập kho'),
            ('cancelled', 'Hủy'),
        ],
        default='posted',
        db_index=True,
        verbose_name='Trạng thái',
    )
    production_order_code = models.CharField(max_length=60, blank=True, default='', verbose_name='Lệnh SX')
    product_code = models.CharField(max_length=80, blank=True, default='', verbose_name='Mã SP')
    fg_receipt = models.ForeignKey(
        'san_xuat.SxFgReceiptRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_receipts',
        verbose_name='Yêu cầu nhập TP',
    )
    notes = models.TextField(blank=True, default='', verbose_name='Ghi chú')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kho_sp_receipts_created',
        verbose_name='Người tạo',
    )
    posted_at = models.DateTimeField(null=True, blank=True, verbose_name='Nhập kho lúc')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kho_sp_stock_receipt'
        ordering = ['-receipt_date', '-pk']
        verbose_name = 'Phiếu nhập kho thành phẩm'
        verbose_name_plural = 'Phiếu nhập kho thành phẩm'

    def __str__(self):
        return self.number


class StockReceiptLine(models.Model):
    receipt = models.ForeignKey(
        StockReceipt,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Phiếu nhập',
    )
    product = models.ForeignKey(
        'kho_san_pham.Product',
        on_delete=models.PROTECT,
        related_name='stock_receipt_lines',
        verbose_name='SKU',
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Số lượng')
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, verbose_name='Đơn giá',
    )
    size_label = models.CharField(max_length=40, blank=True, default='', verbose_name='Size')
    color_label = models.CharField(max_length=40, blank=True, default='', verbose_name='Màu')
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')

    class Meta:
        db_table = 'kho_sp_stock_receipt_line'
        ordering = ['pk']
        verbose_name = 'Dòng phiếu nhập TP'
        verbose_name_plural = 'Dòng phiếu nhập TP'

    def __str__(self):
        return f'{self.receipt.number} · {self.product_id} · {self.quantity}'
