"""Mirror KiotViet trên PostgreSQL portal (bảng prefix kv_)."""

from __future__ import annotations

from django.conf import settings
from django.db import models



class KvSyncState(models.Model):
    entity_type = models.CharField(max_length=32)
    retailer = models.CharField(max_length=64)
    last_modified_from = models.DateTimeField(null=True, blank=True)
    last_full_sync_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    records_total = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'kv_sync_state'
        constraints = [
            models.UniqueConstraint(
                fields=['entity_type', 'retailer'],
                name='kv_sync_state_entity_retailer_uniq',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.retailer}:{self.entity_type}'


class KvSyncTombstone(models.Model):
    entity_type = models.CharField(max_length=32, db_index=True)
    kiotviet_id = models.BigIntegerField()
    retailer = models.CharField(max_length=64, db_index=True)
    removed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kv_sync_tombstone'
        constraints = [
            models.UniqueConstraint(
                fields=['entity_type', 'kiotviet_id', 'retailer'],
                name='kv_sync_tombstone_uniq',
            ),
        ]


class KvRetailerSyncedModel(models.Model):
    retailer = models.CharField(max_length=64, db_index=True)
    kiotviet_id = models.BigIntegerField()
    kv_modified_at = models.DateTimeField(null=True, blank=True, db_index=True)
    synced_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True


class KvBranch(KvRetailerSyncedModel):
    branch_name = models.CharField(max_length=255, blank=True, default='')
    branch_code = models.CharField(max_length=64, blank=True, default='')
    contact_number = models.CharField(max_length=32, blank=True, default='')
    email = models.CharField(max_length=255, blank=True, default='')
    address = models.TextField(blank=True, default='')
    kv_created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'kv_branch'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'kiotviet_id'],
                name='kv_branch_retailer_kid_uniq',
            ),
        ]

    def to_api_dict(self) -> dict:
        return {
            'id': self.kiotviet_id,
            'branchName': self.branch_name,
            'branchCode': self.branch_code,
            'contactNumber': self.contact_number,
            'email': self.email,
            'address': self.address,
            'createdDate': self.kv_created_at,
            'modifiedDate': self.kv_modified_at,
        }


class KvCategory(KvRetailerSyncedModel):
    parent_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    category_name = models.CharField(max_length=255, blank=True, default='')
    has_child = models.BooleanField(default=False)
    kv_created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'kv_category'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'kiotviet_id'],
                name='kv_category_retailer_kid_uniq',
            ),
        ]


class KvProduct(KvRetailerSyncedModel):
    code = models.CharField(max_length=64, blank=True, default='', db_index=True)
    bar_code = models.CharField(max_length=64, blank=True, default='', db_index=True)
    name = models.CharField(max_length=500, blank=True, default='')
    full_name = models.CharField(max_length=500, blank=True, default='')
    description = models.TextField(blank=True, default='')
    category_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    category_name = models.CharField(max_length=255, blank=True, default='')
    unit = models.CharField(max_length=32, blank=True, default='')
    base_price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    weight = models.FloatField(null=True, blank=True)
    allows_sale = models.BooleanField(null=True, blank=True)
    has_variants = models.BooleanField(null=True, blank=True)
    is_active = models.BooleanField(null=True, blank=True)
    product_type = models.SmallIntegerField(null=True, blank=True)
    kv_created_at = models.DateTimeField(null=True, blank=True)
    raw_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'kv_product'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'kiotviet_id'],
                name='kv_product_retailer_kid_uniq',
            ),
        ]

    def to_api_dict(self, *, include_inventory: bool = True) -> dict:
        data = {
            'id': self.kiotviet_id,
            'code': self.code,
            'barCode': self.bar_code,
            'name': self.name,
            'fullName': self.full_name,
            'description': self.description,
            'categoryId': self.category_kiotviet_id,
            'categoryName': self.category_name,
            'unit': self.unit,
            'basePrice': float(self.base_price) if self.base_price is not None else None,
            'weight': self.weight,
            'allowsSale': self.allows_sale,
            'isActive': self.is_active,
            'createdDate': self.kv_created_at,
            'modifiedDate': self.kv_modified_at,
        }
        if include_inventory:
            invs = KvProductInventory.objects.filter(
                retailer=self.retailer,
                product_kiotviet_id=self.kiotviet_id,
                is_deleted=False,
            ).select_related()
            data['inventories'] = [inv.to_api_dict() for inv in invs]
        return data


class KvProductAttribute(models.Model):
    retailer = models.CharField(max_length=64, db_index=True)
    product_kiotviet_id = models.BigIntegerField(db_index=True)
    attribute_name = models.CharField(max_length=255, blank=True, default='')
    attribute_value = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'kv_product_attribute'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'product_kiotviet_id', 'attribute_name', 'attribute_value'],
                name='kv_product_attribute_uniq',
            ),
        ]


class KvProductUnit(models.Model):
    retailer = models.CharField(max_length=64, db_index=True)
    kiotviet_id = models.BigIntegerField()
    product_kiotviet_id = models.BigIntegerField(db_index=True)
    code = models.CharField(max_length=64, blank=True, default='')
    name = models.CharField(max_length=500, blank=True, default='')
    full_name = models.CharField(max_length=500, blank=True, default='')
    unit = models.CharField(max_length=32, blank=True, default='')
    conversion_value = models.FloatField(null=True, blank=True)
    base_price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'kv_product_unit'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'kiotviet_id'],
                name='kv_product_unit_retailer_kid_uniq',
            ),
        ]


class KvProductInventory(models.Model):
    retailer = models.CharField(max_length=64, db_index=True)
    product_kiotviet_id = models.BigIntegerField(db_index=True)
    branch_kiotviet_id = models.BigIntegerField(db_index=True)
    branch_name = models.CharField(max_length=255, blank=True, default='')
    on_hand = models.FloatField(null=True, blank=True)
    reserved = models.FloatField(null=True, blank=True)
    cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    kv_modified_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'kv_product_inventory'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'product_kiotviet_id', 'branch_kiotviet_id'],
                name='kv_product_inventory_uniq',
            ),
        ]

    def to_api_dict(self) -> dict:
        return {
            'productId': self.product_kiotviet_id,
            'branchId': self.branch_kiotviet_id,
            'branchName': self.branch_name,
            'onHand': self.on_hand,
            'reserved': self.reserved,
            'cost': float(self.cost) if self.cost is not None else None,
            'modifiedDate': self.kv_modified_at,
        }


class KvCustomer(KvRetailerSyncedModel):
    code = models.CharField(max_length=64, blank=True, default='', db_index=True)
    name = models.CharField(max_length=255, blank=True, default='')
    gender = models.BooleanField(null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    contact_number = models.CharField(max_length=32, blank=True, default='', db_index=True)
    address = models.TextField(blank=True, default='')
    location_name = models.CharField(max_length=255, blank=True, default='')
    ward_name = models.CharField(max_length=255, blank=True, default='')
    email = models.CharField(max_length=255, blank=True, default='')
    organization = models.CharField(max_length=255, blank=True, default='')
    comments = models.TextField(blank=True, default='')
    tax_code = models.CharField(max_length=32, blank=True, default='')
    debt = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_invoiced = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_revenue = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_point = models.FloatField(null=True, blank=True)
    reward_point = models.BigIntegerField(null=True, blank=True)
    kv_created_at = models.DateTimeField(null=True, blank=True)
    raw_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'kv_customer'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'kiotviet_id'],
                name='kv_customer_retailer_kid_uniq',
            ),
        ]

    def to_api_dict(self) -> dict:
        data = {
            'id': self.kiotviet_id,
            'code': self.code,
            'name': self.name,
            'gender': self.gender,
            'birthDate': self.birth_date.isoformat() if self.birth_date else None,
            'contactNumber': self.contact_number,
            'address': self.address,
            'locationName': self.location_name,
            'wardName': self.ward_name,
            'email': self.email,
            'organization': self.organization,
            'comments': self.comments,
            'taxCode': self.tax_code,
            'debt': float(self.debt) if self.debt is not None else None,
            'totalInvoiced': float(self.total_invoiced) if self.total_invoiced is not None else None,
            'totalRevenue': float(self.total_revenue) if self.total_revenue is not None else None,
            'totalPoint': self.total_point,
            'rewardPoint': self.reward_point,
            'createdDate': self.kv_created_at,
            'modifiedDate': self.kv_modified_at,
        }
        if self.raw_json:
            data.update(self.raw_json)
        return data


class KvOrder(KvRetailerSyncedModel):
    code = models.CharField(max_length=64, blank=True, default='', db_index=True)
    purchase_date = models.DateTimeField(null=True, blank=True, db_index=True)
    branch_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    branch_name = models.CharField(max_length=255, blank=True, default='')
    sold_by_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    sold_by_name = models.CharField(max_length=255, blank=True, default='')
    customer_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    customer_code = models.CharField(max_length=64, blank=True, default='', db_index=True)
    customer_name = models.CharField(max_length=255, blank=True, default='')
    total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_payment = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    status = models.IntegerField(null=True, blank=True)
    status_value = models.CharField(max_length=64, blank=True, default='')
    description = models.TextField(blank=True, default='')
    kv_created_at = models.DateTimeField(null=True, blank=True)
    raw_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'kv_order'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'kiotviet_id'],
                name='kv_order_retailer_kid_uniq',
            ),
        ]

    def to_api_dict(self, *, include_lines: bool = True) -> dict:
        data = {
            'id': self.kiotviet_id,
            'code': self.code,
            'purchaseDate': self.purchase_date,
            'branchId': self.branch_kiotviet_id,
            'branchName': self.branch_name,
            'soldById': self.sold_by_kiotviet_id,
            'soldByName': self.sold_by_name,
            'customerId': self.customer_kiotviet_id,
            'customerCode': self.customer_code,
            'customerName': self.customer_name,
            'total': float(self.total) if self.total is not None else None,
            'totalPayment': float(self.total_payment) if self.total_payment is not None else None,
            'discount': float(self.discount) if self.discount is not None else None,
            'status': self.status,
            'statusValue': self.status_value,
            'description': self.description,
            'createdDate': self.kv_created_at,
            'modifiedDate': self.kv_modified_at,
        }
        if self.raw_json:
            for key in ('payments', 'surcharges'):
                if key in self.raw_json:
                    data[key] = self.raw_json[key]
        if include_lines:
            lines = KvOrderLine.objects.filter(
                retailer=self.retailer,
                order_kiotviet_id=self.kiotviet_id,
            )
            data['orderDetails'] = [line.to_api_dict() for line in lines]
        elif self.raw_json.get('orderDetails'):
            data['orderDetails'] = self.raw_json['orderDetails']
        return data


class KvOrderLine(models.Model):
    retailer = models.CharField(max_length=64, db_index=True)
    order_kiotviet_id = models.BigIntegerField(db_index=True)
    product_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    product_code = models.CharField(max_length=64, blank=True, default='')
    product_name = models.CharField(max_length=500, blank=True, default='')
    quantity = models.FloatField(null=True, blank=True)
    price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True, default='')
    line_index = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'kv_order_line'
        ordering = ['line_index', 'id']

    def to_api_dict(self) -> dict:
        return {
            'productId': self.product_kiotviet_id,
            'productCode': self.product_code,
            'productName': self.product_name,
            'quantity': self.quantity,
            'price': float(self.price) if self.price is not None else None,
            'discount': float(self.discount) if self.discount is not None else None,
            'note': self.note,
        }


class KvInvoice(KvRetailerSyncedModel):
    code = models.CharField(max_length=64, blank=True, default='', db_index=True)
    purchase_date = models.DateTimeField(null=True, blank=True, db_index=True)
    branch_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    branch_name = models.CharField(max_length=255, blank=True, default='')
    sold_by_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    sold_by_name = models.CharField(max_length=255, blank=True, default='')
    customer_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    customer_code = models.CharField(max_length=64, blank=True, default='', db_index=True)
    customer_name = models.CharField(max_length=255, blank=True, default='')
    total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_payment = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    status = models.IntegerField(null=True, blank=True)
    status_value = models.CharField(max_length=64, blank=True, default='')
    kv_created_at = models.DateTimeField(null=True, blank=True)
    raw_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'kv_invoice'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'kiotviet_id'],
                name='kv_invoice_retailer_kid_uniq',
            ),
        ]

    def to_api_dict(self, *, include_lines: bool = True) -> dict:
        data = {
            'id': self.kiotviet_id,
            'code': self.code,
            'purchaseDate': self.purchase_date,
            'branchId': self.branch_kiotviet_id,
            'branchName': self.branch_name,
            'soldById': self.sold_by_kiotviet_id,
            'soldByName': self.sold_by_name,
            'customerId': self.customer_kiotviet_id,
            'customerCode': self.customer_code,
            'customerName': self.customer_name,
            'total': float(self.total) if self.total is not None else None,
            'totalPayment': float(self.total_payment) if self.total_payment is not None else None,
            'status': self.status,
            'statusValue': self.status_value,
            'createdDate': self.kv_created_at,
            'modifiedDate': self.kv_modified_at,
        }
        if self.raw_json:
            for key in ('payments',):
                if key in self.raw_json:
                    data[key] = self.raw_json[key]
        if include_lines:
            lines = KvInvoiceLine.objects.filter(
                retailer=self.retailer,
                invoice_kiotviet_id=self.kiotviet_id,
            )
            data['invoiceDetails'] = [line.to_api_dict() for line in lines]
        elif self.raw_json.get('invoiceDetails'):
            data['invoiceDetails'] = self.raw_json['invoiceDetails']
        return data


class KvInvoiceLine(models.Model):
    retailer = models.CharField(max_length=64, db_index=True)
    invoice_kiotviet_id = models.BigIntegerField(db_index=True)
    product_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    product_code = models.CharField(max_length=64, blank=True, default='')
    product_name = models.CharField(max_length=500, blank=True, default='')
    quantity = models.FloatField(null=True, blank=True)
    price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True, default='')
    line_index = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'kv_invoice_line'
        ordering = ['line_index', 'id']

    def to_api_dict(self) -> dict:
        return {
            'productId': self.product_kiotviet_id,
            'productCode': self.product_code,
            'productName': self.product_name,
            'quantity': self.quantity,
            'price': float(self.price) if self.price is not None else None,
            'discount': float(self.discount) if self.discount is not None else None,
            'note': self.note,
        }


class KvPurchaseOrder(KvRetailerSyncedModel):
    code = models.CharField(max_length=64, blank=True, default='', db_index=True)
    purchase_date = models.DateTimeField(null=True, blank=True, db_index=True)
    branch_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    branch_name = models.CharField(max_length=255, blank=True, default='')
    supplier_code = models.CharField(max_length=64, blank=True, default='')
    supplier_name = models.CharField(max_length=255, blank=True, default='')
    partner_type = models.CharField(max_length=64, blank=True, default='')
    purchase_name = models.CharField(max_length=255, blank=True, default='')
    total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    status = models.IntegerField(null=True, blank=True)
    status_value = models.CharField(max_length=64, blank=True, default='')
    raw_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'kv_purchase_order'
        constraints = [
            models.UniqueConstraint(
                fields=['retailer', 'kiotviet_id'],
                name='kv_purchase_order_retailer_kid_uniq',
            ),
        ]

    def to_api_dict(self, *, include_lines: bool = True) -> dict:
        data = {
            'id': self.kiotviet_id,
            'code': self.code,
            'purchaseDate': self.purchase_date,
            'branchId': self.branch_kiotviet_id,
            'branchName': self.branch_name,
            'supplierCode': self.supplier_code,
            'supplierName': self.supplier_name,
            'partnerType': self.partner_type,
            'purchaseName': self.purchase_name,
            'total': float(self.total) if self.total is not None else None,
            'status': self.status,
            'statusValue': self.status_value,
            'modifiedDate': self.kv_modified_at,
        }
        if include_lines:
            lines = KvPurchaseOrderLine.objects.filter(
                retailer=self.retailer,
                purchase_order_kiotviet_id=self.kiotviet_id,
            )
            data['purchaseOrderDetails'] = [line.to_api_dict() for line in lines]
        elif self.raw_json.get('purchaseOrderDetails'):
            data['purchaseOrderDetails'] = self.raw_json['purchaseOrderDetails']
        return data


class KvPurchaseOrderLine(models.Model):
    retailer = models.CharField(max_length=64, db_index=True)
    purchase_order_kiotviet_id = models.BigIntegerField(db_index=True)
    product_kiotviet_id = models.BigIntegerField(null=True, blank=True)
    product_code = models.CharField(max_length=64, blank=True, default='')
    product_name = models.CharField(max_length=500, blank=True, default='')
    quantity = models.FloatField(null=True, blank=True)
    price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    line_index = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'kv_purchase_order_line'
        ordering = ['line_index', 'id']

    def to_api_dict(self) -> dict:
        return {
            'productId': self.product_kiotviet_id,
            'productCode': self.product_code,
            'ProductCode': self.product_code,
            'productName': self.product_name,
            'quantity': self.quantity,
            'price': float(self.price) if self.price is not None else None,
            'discount': float(self.discount) if self.discount is not None else None,
        }


class KvSyncConfig(models.Model):
    """Cấu hình đồng bộ KiotViet (một bản ghi / retailer)."""

    retailer = models.CharField(max_length=64, unique=True)
    interval_hours = models.PositiveSmallIntegerField(default=2)
    schedule_enabled = models.BooleanField(default=True)
    enabled_entities = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kv_sync_configs_updated',
    )

    class Meta:
        db_table = 'kv_sync_config'
        verbose_name = 'Cấu hình đồng bộ KiotViet'
        verbose_name_plural = 'Cấu hình đồng bộ KiotViet'

    def __str__(self) -> str:
        return f'{self.retailer} · {self.interval_hours}h'

    @classmethod
    def get_for_retailer(cls, retailer: str) -> KvSyncConfig:
        from .sync_service import ENTITY_ALL

        obj, _ = cls.objects.get_or_create(
            retailer=retailer,
            defaults={'enabled_entities': list(ENTITY_ALL)},
        )
        if not obj.enabled_entities:
            obj.enabled_entities = list(ENTITY_ALL)
        return obj


class KvSyncJob(models.Model):
    TRIGGER_MANUAL = 'manual'
    TRIGGER_SCHEDULED = 'scheduled'
    TRIGGER_CHOICES = [
        (TRIGGER_MANUAL, 'Thủ công'),
        (TRIGGER_SCHEDULED, 'Tự động'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Chờ'),
        (STATUS_RUNNING, 'Đang chạy'),
        (STATUS_SUCCESS, 'Thành công'),
        (STATUS_FAILED, 'Thất bại'),
    ]

    trigger = models.CharField(max_length=16, choices=TRIGGER_CHOICES, default=TRIGGER_MANUAL)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    full_sync = models.BooleanField(default=False)
    entities = models.JSONField(default=list, blank=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    current_entity = models.CharField(max_length=32, blank=True, default='')
    rows_synced = models.BigIntegerField(default=0)
    message = models.TextField(blank=True, default='')
    entity_results = models.JSONField(default=list, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kv_sync_jobs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'kv_sync_job'
        ordering = ['-created_at']
        verbose_name = 'Job đồng bộ KiotViet'
        verbose_name_plural = 'Job đồng bộ KiotViet'

    def __str__(self) -> str:
        return f'{self.get_trigger_display()} · {self.get_status_display()} · {self.progress_percent}%'

    @property
    def duration_display(self) -> str:
        if not self.started_at or not self.finished_at:
            return '—'
        delta = self.finished_at - self.started_at
        secs = int(delta.total_seconds())
        if secs < 60:
            return f'{secs}s'
        return f'{secs // 60} phút {secs % 60}s'

    @property
    def is_active(self) -> bool:
        return self.status in (self.STATUS_PENDING, self.STATUS_RUNNING)

