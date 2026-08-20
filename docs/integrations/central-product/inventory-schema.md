# Kho thành phẩm trung tâm — thiết kế

Tiếp nối [sku-vocabulary.md](./sku-vocabulary.md) (từ vựng SKU đã chuẩn hóa xong
20/08/2026). Bước 2-3 và 5-6 của lộ trình đã hiện thực — xem mục 12.

## 0. Các quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Đặt central ở đâu | **Là app trong Portal** — mở rộng `kho_san_pham`, không dựng VPS riêng |
| Truy vết theo lô / ngày SX | **Không** — tồn chỉ theo `(SKU, kho)` |
| Bán quá tồn | **Không chặn** — central vẫn ghi, tồn âm thì báo động |
| Giá thành nhập kho | **Đẩy kèm khi có**, không bắt buộc — xem mục 0.1 |
| Danh sách kho / điểm bán | 2 kho: `XUONG-TP` (portal), `CH-TRUNG-TAM` (sales) |

### 0.1 Vì sao giá thành không còn là ràng buộc bắt buộc

Thiết kế ban đầu bắt `production_in` phải kèm `unit_cost`. Khi nối vào `san_xuat` mới
thấy dữ liệu thật không cho phép:

- `SxActualCostSheet` (giá thành thực tế) — **0 dòng**, module chưa dùng.
- `SxStandardCostSheet` (giá định mức) — 1 bảng đã chốt, nhưng chỉ **5 mã hàng**.

Bắt buộc có giá nghĩa là **xưởng không nhập kho được thành phẩm cho đến khi kế toán dựng
xong giá thành**. Đó là ràng buộc sai chỗ: mục đích chính của sổ kho là *số lượng* đúng,
giá vốn là phần phụ và tính được sau. Chặn nhập kho vì thiếu giá là đánh đổi cái chính lấy
cái phụ.

Nên `unit_cost` để `null=True`, và **`None` khác 0**: `None` là chưa biết giá, `0` là
khẳng định sản phẩm không có chi phí. Giữ được phân biệt này thì
`kho_san_pham.services.stock.entries_missing_cost()` truy ra đúng những dòng cần điền bù;
ghi 0 cho "chưa biết" là tự tay tạo dữ liệu sai không cách nào phát hiện lại.

Thiết kế soi theo hai khuôn **đã chạy thật trong Portal**, không dựng mô hình mới:

| Khuôn có sẵn | Dùng cho |
|---|---|
| `kho_npl.StockBalance` + `StockLedger` | Số dư tồn và sổ kho append-only |
| `kho_npl.services.*` (`select_for_update` + `atomic`) | Chống tranh chấp khi ghi tồn |
| `kiotviet.KvRetailerSyncedModel` (`kv_modified_at`) | Đồng bộ tăng dần bằng watermark |
| `kiotviet.KvSyncTombstone` | Truyền lệnh xóa qua biên hệ thống |

## 1. Kiến trúc sau khi chốt

Vì central là app trong Portal, chỉ còn **hai** hệ thống và **một** biên mạng:

```
┌─────────────── Portal (VPS 1) ────────────────┐
│                                               │
│  san_xuat          kho_san_pham               │        Bán hàng (VPS 2)
│  ─────────         ────────────               │        ────────────────
│  Nhập TP  ──cùng──▶ Product (danh mục SKU)    │        Bán / trả hàng
│           transaction StockBalance  ◀─────────┼──HTTP── (qua outbox)
│                     StockLedger               │
│                     Warehouse                 │──HTTP──▶ kéo danh mục SKU
└───────────────────────────────────────────────┘
```

Lựa chọn này bỏ được hai thứ so với phương án server riêng:

- **Không cần bảng SKU bản sao.** `kho_san_pham.Product` đã *chính là* bảng SKU: 2.900
  dòng đã chuẩn hóa màu/size/giới tính và đã nối `sx_sku`. Dựng thêm một bảng `Sku` ở
  server thứ ba là tạo thêm một bản sao có thể lệch.
- **Không cần outbox cho chiều nhập.** Portal ghi tồn trong *cùng transaction* với
  `SxFgReceiptRequest` — không có biên mạng thì không có phát sinh nào để mất.

Đây cũng chính là việc "thiết kế lại kho sản phẩm": `kho_san_pham` hiện chỉ có duy nhất
model `Product` (một bản sao sản phẩm KiotViet, không có tồn), sau thiết kế này nó mới
thực sự thành cái kho.

Rủi ro đã nhận diện: Portal chết thì bán hàng không đẩy được phát sinh. Outbox ở phía bán
hàng xử lý đúng tình huống này — phát sinh nằm chờ và tự gửi lại khi Portal sống lại,
không mất gì (mục 7).

## 2. Ai sở hữu dữ liệu gì

Quy tắc: **một dữ liệu chỉ có một chủ ghi.** Hai nơi cùng ghi một trường là nguồn gốc của
mọi lệch dữ liệu.

| Dữ liệu | Chủ ghi | Nơi khác |
|---|---|---|
| Định nghĩa SKU (style, màu, size, giới tính, tên) | **Portal** `kho_san_pham.Product` | Bán hàng chỉ đọc |
| Từ vựng màu / size | **Portal** `SxColor` / `SxSize` | đẩy kèm SKU |
| Danh sách kho / điểm bán | **Portal** `Warehouse` | Bán hàng đọc |
| Số dư tồn | **Portal** `StockBalance` | không ai ghi trực tiếp |
| Phát sinh nhập từ sản xuất | **Portal** `san_xuat` | ghi thẳng, cùng transaction |
| Phát sinh bán / trả | **Bán hàng** | đẩy qua HTTP |
| Giá bán, khuyến mãi, khách hàng | **Bán hàng** | Portal không giữ |

Hệ quả quan trọng: **VPS bán hàng không bao giờ tạo SKU.** Bán một mặt hàng chưa có SKU
là lỗi nghiệp vụ cần chặn tại chỗ, không phải tự tạo mã mới — nếu cho tạo thì hai bên sẽ
sinh hai mã cho cùng một sản phẩm và không cách nào gộp lại.

## 3. Vì sao không dùng message broker

Đã cân nhắc Kafka / RabbitMQ / Redis Stream và **không dùng**. Lý do cụ thể, không phải
chống lại event-driven về nguyên tắc:

- Sau khi chốt phương án app-trong-Portal thì chỉ còn **một** hệ đẩy dữ liệu qua mạng
  (bán hàng), vài nghìn phát sinh mỗi ngày. Broker giải bài toán thông lượng và fan-out
  nhiều consumer mà ở đây không tồn tại.
- Broker là một dịch vụ nữa phải vận hành, sao lưu, giám sát. Portal chưa có
  Celery/Redis worker; thêm broker là thêm một hệ có thể chết lúc 2 giờ sáng.
- Phần giá trị thật của event-driven — **không mất phát sinh khi mạng lỗi** — đến từ
  *transactional outbox*, và outbox chỉ cần một bảng Postgres.

Cái cần lấy từ event-driven là ba tính chất, cả ba đạt được mà không cần broker:

1. **Ghi sổ append-only.** Tồn là kết quả cộng dồn của phát sinh, không phải con số bị ghi
   đè. Sai thì ghi bút toán đảo, không sửa lịch sử.
2. **Chống trùng.** Gửi lại cùng một phát sinh không được cộng tồn hai lần (mục 6).
3. **Bền với lỗi mạng.** Phát sinh và ý định gửi nằm trong cùng transaction (mục 7).

> **Bài học phải tránh.** Portal đang chạy job nền bằng `threading.Thread(daemon=True)`
> (`kiotviet/odoo_push_runner.py`, `reports/nas_pending_sync.py`). Container restart lúc
> deploy là job chết giữa đường, `KvSyncJob` treo ở `RUNNING` vĩnh viễn và chặn mọi job
> sau. **Worker mới phải do cron gọi management command**, không dùng thread nền.

## 4. Danh mục SKU — dùng lại `Product`, không thêm bảng

Không có model mới. `kho_san_pham.Product` đã có đủ: `code` (mã SKU, unique), `name`,
`full_name`, `unit`, `is_active`, `sx_sku`, cùng `color_code` / `size_label` / `gender` đã
chuẩn hóa. Thang size và thứ tự sắp xếp lấy từ `SxSize.scale` / `sort_order`.

Chỉ cần thêm **một trường** để phục vụ đồng bộ tăng dần cho VPS bán hàng, theo đúng khuôn
`kv_modified_at`:

```python
# kho_san_pham/models.py — Product
catalog_updated_at = models.DateTimeField(auto_now=True, db_index=True)
```

Đây là watermark cho `GET /api/v1/skus?since=...`. Không có nó thì bán hàng buộc phải kéo
toàn bộ 2.900 SKU mỗi lần.

Xóa SKU dùng **tombstone** thay vì DELETE, theo khuôn `KvSyncTombstone`: bên kéo không có
cách nào biết một bản ghi đã biến mất nếu nó chỉ đơn giản không còn trong danh sách.

```python
class ProductTombstone(models.Model):
    product_code = models.CharField(max_length=100, unique=True)
    removed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'kho_sp_product_tombstone'
```

Thực tế SKU gần như không bao giờ xóa — chỉ `is_active=False`, và bán hàng thấy được qua
đồng bộ thường. Tombstone dành riêng cho trường hợp tạo nhầm mã.

## 5. Kho và tồn — model mới trong `kho_san_pham`

Đặt tên bảng theo tiền tố sẵn có của app (`kho_sp_product`).

### Kho

```python
class Warehouse(models.Model):
    OWNER_PORTAL = 'portal'    # kho thành phẩm tại xưởng
    OWNER_SALES = 'sales'      # cửa hàng / kho bán hàng

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    owner_system = models.CharField(max_length=20, choices=..., db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'kho_sp_warehouse'
```

`SxFgReceiptRequest` hiện có `warehouse_code` / `warehouse_name` dạng **chữ tự do**. Khi
tích hợp phải chuyển sang FK trỏ `Warehouse` — để chữ tự do thì tồn sẽ rơi vào kho sai vì
lỗi chính tả mà không ai phát hiện.

Dữ liệu thật (tra ngày 20/08/2026) cho thấy việc chuyển đổi này gần như không tốn gì:

```
warehouse_code | warehouse_name | so_phieu |  tu_ngay   |  den_ngay
kv:4           | Xưởng sản xuất |        1 | 2026-08-11 | 2026-08-11
```

**Chỉ 1 phiếu nhập thành phẩm từng được tạo**, và chỉ 1 mã kho. Tính năng nhập thành phẩm
mới dùng thử chứ chưa vận hành thật, nên đổi sang FK không cần migration dữ liệu phức tạp
và không có lịch sử tồn nào phải bảo toàn.

Mã `kv:4` là id chi nhánh KiotViet — quy ước tạm vì `kv_branch.branch_code` đang trống.
`Warehouse.code` nên đặt mã nghiệp vụ đọc được, đừng kế thừa `kv:<id>`: khi bỏ KiotViet
thì con số 4 không còn nghĩa gì.

### Số dư tồn

Y khuôn `kho_npl.StockBalance`, thay `material` bằng `product`:

```python
class StockBalance(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='balances')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='balances')
    qty_on_hand = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kho_sp_stock_balance'
        unique_together = [('product', 'warehouse')]
```

Ba chi tiết có chủ ý:

- **`decimal_places=2`** để khớp `SxFgReceiptRequest.qty` bên `san_xuat`. Lệch độ chính
  xác giữa hai bảng là chỗ sinh sai số làm tròn.
- **`PROTECT` thay vì `CASCADE`** — xóa một SKU đã có phát sinh tồn phải là lỗi, không
  phải hành động im lặng. (`kho_npl` dùng `CASCADE` cho `material`; đây là chỗ tôi cố ý
  không sao y.)
- **Không có `MinValueValidator(0)`**, khác `kho_npl`. Lý do ở mục 8.

Đã chốt không truy vết lô, nên khóa chỉ hai chiều `(product, warehouse)`. Nếu sau này
nghiệp vụ cần lô thì phải chia lại toàn bộ số dư đang có — đó là lý do câu hỏi này được
đặt ra trước khi viết code chứ không để sau.

### Sổ kho

```python
class StockLedger(models.Model):
    # Loại phát sinh — soi theo ref_type của kho_npl.StockLedger
    KIND_PRODUCTION_IN = 'production_in'    # nhập thành phẩm từ sản xuất
    KIND_SALE_OUT = 'sale_out'              # bán
    KIND_SALE_RETURN_IN = 'sale_return_in'  # khách trả
    KIND_TRANSFER_OUT = 'transfer_out'
    KIND_TRANSFER_IN = 'transfer_in'
    KIND_ADJUST = 'adjust'                  # kiểm kê / điều chỉnh
    KIND_DISPOSAL_OUT = 'disposal_out'      # hủy

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='ledger_entries')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='ledger_entries')
    kind = models.CharField(max_length=24, db_index=True)
    qty_delta = models.DecimalField(max_digits=14, decimal_places=2)      # âm khi xuất
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Khóa chống trùng — mục 6
    source_system = models.CharField(max_length=20, db_index=True)   # portal | sales
    source_doc_type = models.CharField(max_length=30)
    source_doc_code = models.CharField(max_length=60, db_index=True)
    source_line_no = models.PositiveIntegerField(default=1)

    occurred_at = models.DateTimeField(db_index=True)      # thời điểm nghiệp vụ
    received_at = models.DateTimeField(auto_now_add=True)  # thời điểm ghi sổ
    actor = models.CharField(max_length=150, blank=True, default='')
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'kho_sp_stock_ledger'
        ordering = ['-occurred_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['source_system', 'source_doc_type', 'source_doc_code', 'source_line_no'],
                name='kho_sp_ledger_source_uniq',
            ),
        ]
        indexes = [models.Index(fields=['product', 'warehouse', 'occurred_at'])]
```

Tách `occurred_at` khỏi `received_at` là chi tiết dễ bỏ qua nhưng cần thiết: cửa hàng bán
lúc 20h, mạng lỗi, phát sinh về Portal lúc 23h. Báo cáo doanh thu phải dùng `occurred_at`,
truy vết sự cố đồng bộ phải dùng `received_at`. Gộp một trường là mất một trong hai.

`unit_cost` để `null=True` dù đã chốt đẩy kèm giá thành: phát sinh **xuất** thì giá vốn là
kết quả tính từ tồn chứ không phải dữ liệu bên gửi cấp. Ràng buộc "bắt buộc có giá" chỉ áp
cho `production_in`, và kiểm ở tầng service — không phải ở cột.

## 6. Khóa chống trùng — phần cốt tử

Nếu làm sai chỗ này thì mọi thứ khác vô nghĩa: **mạng lỗi thì bên gửi không biết Portal đã
ghi hay chưa.** Gửi lại là chuyện bắt buộc, nên Portal phải nhận diện được "cái này tôi
ghi rồi".

Khóa là bốn trường `(source_system, source_doc_type, source_doc_code, source_line_no)`.
Bên gửi phải cấp khóa từ **chứng từ gốc** của nó — tuyệt đối không dùng UUID sinh lúc gửi,
vì gửi lại sẽ ra UUID khác và mất sạch tác dụng.

| Nguồn | `source_doc_type` | `source_doc_code` | `source_line_no` |
|---|---|---|---|
| `san_xuat` — nhập thành phẩm | `fg_receipt` | `SxFgReceiptRequest.code` | `SxFgReceiptLine.pk` |
| Bán hàng — hóa đơn | `invoice` | số hóa đơn | số dòng hóa đơn |
| Bán hàng — trả hàng | `sale_return` | số phiếu trả | số dòng |
| Kiểm kê | `stocktake` | số phiếu kiểm kê | số dòng |

Với YCNTP, `source_line_no` dùng **id dòng** chứ không phải số thứ tự. Số thứ tự đổi khi
người dùng thêm hoặc xóa dòng, và khi đó lần ghi sau sẽ bị coi là phát sinh mới thay vì
gửi trùng — đúng cái mà khóa này tồn tại để ngăn.

Hàm ghi sổ duy nhất là `kho_san_pham.services.stock.post_movement`, đúng khuôn
`kho_npl.services`:

```python
@transaction.atomic
def post_movement(*, product, warehouse, kind, qty_delta, source, occurred_at, ...):
    _validate(...)   # dấu số lượng, quyền ghi theo kho, giá thành — mục 6.1

    # 1. Khóa dòng số dư TRƯỚC khi kiểm chống trùng
    balance, _ = (
        StockBalance.objects
        .select_for_update()
        .get_or_create(product=product, warehouse=warehouse,
                       defaults={'qty_on_hand': Decimal('0')})
    )

    # 2. Giờ mới kiểm — và so cả nội dung, không chỉ sự tồn tại
    existing = StockLedger.objects.filter(**source_key).first()
    if existing is not None:
        if _describe_conflicts(existing, ...):
            raise StockMovementError('...đã ghi với nội dung khác...')
        return AlreadyApplied

    # 3. Cộng dồn rồi ghi sổ — balance_after chắc đúng vì đang giữ khóa
    balance.qty_on_hand += qty_delta
    balance.save(update_fields=['qty_on_hand', 'updated_at'])
    entry = StockLedger.objects.create(..., balance_after=balance.qty_on_hand)

    # 4. Tồn âm thì báo động, không chặn — mục 8
    if balance.qty_on_hand < 0:
        NegativeStockAlert.objects.create(ledger_entry=entry, ...)
```

**Thứ tự khóa rồi mới kiểm** là có lý do. Hai request đẩy trùng cùng một phát sinh thì
nhất thiết cùng `(SKU, kho)`, nên chúng tuần tự hóa ở dòng số dư — kiểm *sau* khi có khóa
mới thấy được dòng mà request kia vừa ghi. Kiểm trước rồi mới khóa thì cả hai đều thấy
"chưa có" và cộng tồn hai lần. Bản thiết kế đầu tiên đặt ngược thứ tự này.

**So cả nội dung, không chỉ sự tồn tại của khóa.** Nếu bên gửi dùng lại số chứng từ cho
một SKU hoặc số lượng khác, trả về "đã ghi" là âm thầm làm mất phát sinh mới — im lặng
đúng ở ca gửi trùng nhưng sai ở ca trùng khóa. Nên khi khóa đã tồn tại mà nội dung lệch,
hàm báo `StockMovementError` kèm chỉ rõ lệch ở đâu.

Ràng buộc duy nhất ở DB vẫn là chốt cuối cho tình huống hai request khác `(SKU, kho)` cùng
khóa lọt qua đồng thời — `IntegrityError` được chuyển thành `StockMovementError` có thông
báo đọc được, chứ không phải lỗi 500.

**Mọi đường ghi tồn đều phải đi qua hàm này**, kể cả chiều nhập nội bộ từ `san_xuat`. Có
một chỗ ghi `StockBalance` trực tiếp là mất luôn bảo đảm `balance_after` khớp sổ. Vì thế
`StockBalance` và `StockLedger` để chỉ-đọc trong admin.

### 6.1 Chặn dữ liệu sai ngay ở cửa

Ba lớp kiểm, chạy trước khi chạm DB:

| Kiểm | Vì sao cần |
|---|---|
| Dấu của `qty_delta` khớp loại phát sinh (`MOVEMENT_DIRECTION`) | Một `sale_out` mang số dương sẽ **làm phồng tồn** thay vì báo lỗi. Chỉ `adjust` được đi cả hai chiều. |
| Kho phải thuộc hệ đúng (`MOVEMENT_REQUIRED_OWNER`) | `production_in` chỉ vào kho `portal`, `sale_out` chỉ vào kho `sales`. Chuyển kho và điều chỉnh cố ý không giới hạn. |
| `unit_cost` nếu có thì không được âm | Giá âm là dữ liệu sai. Để trống thì hợp lệ (mục 0.1). |

`StockMovementError` mang nghĩa **bên gửi phải sửa rồi mới gửi lại** — khác lỗi mạng. Bên
gửi nhận lỗi này thì đừng thử lại y nguyên, vì gửi lại cũng sai.

### 6.2 Sửa phát sinh ghi sai

`reverse_movement(entry, reason=...)` ghi một dòng ngược chiều (`kind=adjust`, số chứng từ
`<mã gốc>~REV`) chứ không sửa và không xóa dòng cũ. Mất lịch sử là mất khả năng giải thích
vì sao tồn ra con số hiện tại.

## 7. Hai chiều ghi tồn

### Chiều nhập từ `san_xuat` — không cần outbox

**Đã hiện thực.** Vì cùng một database, `san_xuat.services.fg_stock.post_fg_receipt_to_stock`
gọi thẳng `post_movement` trong transaction chuyển `SxFgReceiptRequest` sang `done`. Nhập
kho và ghi tồn cùng commit hoặc cùng rollback, không có trạng thái lỡ dở.

Đây là phần lời rõ nhất của phương án app-trong-Portal: nếu central ở VPS riêng thì chiều
này cần outbox, cron, retry, và xử lý ca "đã nhập nhưng central chưa nhận".

Hai chỗ phiếu chuyển sang `done` (`submit_fg_receipt` khi tắt yêu cầu liên kết KiotViet, và
`link_kv_purchase`) đều gọi cùng hàm đó. Gọi trùng vô hại vì khóa chống trùng.

**Ghi tồn thất bại thì chặn luôn việc hoàn thành phiếu.** Lỗi được đổi thành `DispatchError`
và transaction rollback cả việc đổi trạng thái — vì phiếu `done` mà tồn không tăng là sai
lệch âm thầm, không ai biết để sửa. Đã kiểm: gửi phiếu có SKU lạ thì phiếu vẫn nằm ở nháp.

Nối SKU đi theo hai đường, do dữ liệu thật buộc phải vậy: ưu tiên FK `SxFgReceiptLine.sku`,
nhưng **6/6 dòng YCNTP hiện có đều để trống FK này**, chỉ có `sku_code` — nên phải lùi về
khớp `sku_code` với `Product.code`. Không tìm được SKU thì chặn: không thể nhập kho một mã
chưa có trong danh mục.

Giá thành lấy qua `resolve_unit_standard_cost(mo.product_code)` có sẵn trong
`plan_costing`; hàm đó trả `Decimal("0")` khi không tra được, nên `fg_stock` đổi 0 thành
`None` để giữ đúng nghĩa "chưa biết giá" (mục 0.1).

### Chiều bán từ VPS bán hàng — outbox ở phía bán hàng

Bảng outbox nằm ở **bên gửi**. Cốt lõi: phát sinh bán và dòng outbox ghi trong **cùng
transaction**. Rollback thì mất cả hai; commit thì còn cả hai. Không có cửa sổ nào mà "đã
bán nhưng chưa có ý định gửi".

```python
# Trên VPS bán hàng
class StockOutbox(models.Model):
    doc_type = models.CharField(max_length=30)
    doc_code = models.CharField(max_length=60)
    line_no = models.PositiveIntegerField(default=1)
    payload = models.JSONField()

    status = models.CharField(max_length=16, default='pending', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['doc_type', 'doc_code', 'line_no'],
                                    name='stock_outbox_doc_uniq'),
        ]
```

Worker là **management command do cron gọi**, không phải thread nền:

```bash
*/2 * * * * docker compose run --rm web python manage.py push_stock_outbox
```

Lấy các dòng `pending` đã tới `next_attempt_at`, khóa bằng
`select_for_update(skip_locked=True)`, POST sang Portal, đánh `sent`. Lỗi thì tăng
`attempts` và giãn `next_attempt_at` lũy tiến. Vì Portal chống trùng theo mục 6, gửi lại
luôn an toàn.

`skip_locked` là chi tiết quan trọng: nó khiến hai lần cron chạy chồng nhau trở thành vô
hại, thay vì phải dựa vào một cờ "đang chạy" — **chính loại cờ đã làm `KvSyncJob` treo
vĩnh viễn**.

## 8. Tồn âm: phải cho phép, và phải báo động

Đây là điểm thiết kế đi ngược bản năng "chặn tồn âm" của `kho_npl`, và đã được chốt.

`kho_npl` chặn được vì nó *là* nơi thực hiện xuất kho: người dùng bấm xuất, hệ thống kiểm
tồn, không đủ thì từ chối — hàng vẫn còn trên kệ. Kho thành phẩm **không** ở vị trí đó khi
nhận phát sinh từ bán hàng: cửa hàng đã bán xong mới đẩy lên, hàng đã ra khỏi kệ và tiền
đã thu. Từ chối vì "tồn không đủ" là làm mất phát sinh thật và khiến sổ sách lệch xa hơn
thực tế.

| Trường hợp | Xử lý |
|---|---|
| Phát sinh đẩy về làm tồn âm | **Vẫn ghi**, tạo `NegativeStockAlert`, thông báo |
| Xuất kho do người dùng bấm ngay trong Portal | **Chặn** như `kho_npl` — hàng còn trên kệ |

Tồn âm là **triệu chứng**, không phải nguyên nhân. Nó chỉ ra một trong ba việc: có phát
sinh nhập chưa đẩy lên, bán hai lần cùng một món, hoặc tồn đầu kỳ nhập sai. Chặn ghi là
bịt miệng triệu chứng và mất luôn dữ liệu để chẩn đoán.

```python
class NegativeStockAlert(models.Model):
    ledger_entry = models.OneToOneField(StockLedger, on_delete=models.CASCADE)
    product_code = models.CharField(max_length=100, db_index=True)
    warehouse_code = models.CharField(max_length=40)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'kho_sp_negative_stock_alert'
```

## 9. Hợp đồng API

Bốn endpoint, chỉ dùng cho VPS bán hàng. Tất cả nhận `Authorization: Bearer <token>`.

**`POST /api/v1/stock/movements`** — đẩy phát sinh theo lô.

```json
{
  "source_system": "sales",
  "movements": [
    {
      "source_doc_type": "invoice",
      "source_doc_code": "HD-2026-018342",
      "source_line_no": 1,
      "kind": "sale_out",
      "sku_code": "SP003537",
      "warehouse_code": "CH-NGUYEN-TRAI",
      "qty_delta": "-2.00",
      "occurred_at": "2026-08-20T20:14:00+07:00",
      "actor": "cashier.03"
    }
  ]
}
```

Đáp lại nêu rõ từng dòng, phân biệt **ghi mới** với **đã có** — bên gửi cần biết để đánh
`sent` mà không lo ghi trùng:

```json
{
  "results": [
    {"source_doc_code": "HD-2026-018342", "source_line_no": 1,
     "status": "applied", "balance_after": "18.00", "warning": null}
  ]
}
```

`status` nhận ba giá trị: `applied`, `already_applied`, `rejected`. Chỉ `rejected` (SKU
không tồn tại, kho không tồn tại) mới là lỗi cần người xử lý — hai giá trị kia đều cho
phép bên gửi đánh `sent`. Tồn âm trả về `applied` kèm `warning`, **không** phải `rejected`.

**`GET /api/v1/skus?since=<iso8601>&cursor=<id>`** — kéo danh mục tăng dần theo watermark
`Product.catalog_updated_at`, trả kèm từ điển màu/size và danh sách tombstone.

**`GET /api/v1/stock/balances?warehouse=<code>&sku=<code>`** — đọc tồn.

**`POST /api/v1/stock/reconcile`** — đối soát, mục 10.

## 10. Đối soát định kỳ

Sổ kho hai bên thì sẽ lệch — không phải nếu, mà là khi nào. Nguyên nhân thường gặp: phát
sinh bị xóa thủ công ở bên gửi sau khi đã đẩy, hoặc sửa DB trực tiếp.

Job hằng đêm: bán hàng gửi lên số dư nó *tin là đúng* cho các kho nó sở hữu; Portal so với
số của mình và xuất bảng lệch. **Không tự sửa** — lệch tồn phải có người nhìn, vì tự căn
chỉnh sẽ che mất nguyên nhân gốc và biến một lỗi rõ ràng thành nhiễu nền.

Chỉ so `(sku, warehouse, qty)`, nhẹ: 2.900 SKU × số kho, dưới một giây.

## 11. Bảo mật

API **chỉ lắng nghe trên interface Tailscale**, không mở ra Internet. Đây là lớp bảo vệ
mạnh nhất và gần như miễn phí — kể cả khi token bị lộ, kẻ tấn công vẫn phải ở trong
tailnet.

Thêm hai lớp: token riêng cho từng hệ (thu hồi độc lập, log biết ai ghi), và kiểm
`owner_system` — token bán hàng không được ghi phát sinh vào kho của xưởng.

## 12. Lộ trình

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Chốt danh sách kho (mục 13) | **Xong** — 2 kho, 20/08/2026 |
| 2 | `Warehouse` + command nạp danh sách kho | **Xong** — `kho_sp_seed_warehouses` |
| 3 | `StockBalance` + `StockLedger` + `post_movement` | **Xong** — migration `0009`, 20/20 kiểm chứng đạt |
| 4 | Tồn đầu kỳ: kiểm kê thực tế, ghi `kind=adjust` | **Form danh mục + lệnh CSV** — `Product.qty_on_hand` là bản sao tồn xưởng |
| 5 | `SxFgReceiptRequest.warehouse_code` → FK `Warehouse` | **Xong** — migration `0085` + `0086` |
| 6 | Nối chiều nhập: `san_xuat` gọi `post_movement` | **Xong** — `fg_stock.py`, 33/33 kiểm chứng đạt |
| 7 | `Product.catalog_updated_at` + API kéo danh mục | Cho bán hàng |
| 8 | API nhận phát sinh + outbox phía bán hàng | Sau khi 6 chạy ổn |
| 9 | Đối soát hằng đêm + cảnh báo tồn âm | |
| 10 | Chuyển kho, kiểm kê, giữ chỗ, giá vốn xuất | Giai đoạn sau |

### Đã hiện thực ở bước 2-3

| Tệp | Nội dung |
|---|---|
| `kho_san_pham/stock_models.py` | `Warehouse`, `StockBalance`, `StockLedger`, `NegativeStockAlert` |
| `kho_san_pham/choices.py` | Loại phát sinh, loại chứng từ, `MOVEMENT_DIRECTION`, `DEFAULT_WAREHOUSES` |
| `kho_san_pham/services/stock.py` | `post_movement`, `reverse_movement`, `get_qty_on_hand`, `set_catalog_qty` |
| `kho_san_pham/migrations/0009_…` | Tạo 4 bảng + ràng buộc chống trùng |
| `kho_san_pham/management/commands/kho_sp_seed_warehouses.py` | Nạp kho, chạy lại được nhiều lần |
| `kho_san_pham/management/commands/kho_sp_import_stocktake.py` | Nhập kiểm kê / tồn đầu kỳ (mục 14) |
| `kho_san_pham/admin.py` | Tồn và sổ kho để chỉ-đọc |
| `scripts/verify_kho_sp_stock.py` | 38 kiểm chứng, chạy trong transaction rồi rollback |

### Đã hiện thực ở bước 5-6

| Tệp | Nội dung |
|---|---|
| `san_xuat/hub_models.py` | `SxFgReceiptRequest.warehouse` FK; hai cột chữ cũ thành dấu vết |
| `san_xuat/migrations/0085_…`, `0086_…` | Thêm FK và ánh xạ `kv:4` → `XUONG-TP` |
| `san_xuat/services/fg_stock.py` | `post_fg_receipt_to_stock`, nối SKU, giá thành, kho |
| `san_xuat/services/dispatch.py` | Móc vào `submit_fg_receipt` và `link_kv_purchase` |
| `san_xuat/forms_dispatch.py` | `fg_warehouse_choices` đọc `Warehouse` thay vì chi nhánh KiotViet |

### Đã lên production 20/08/2026

Commit `91cf7237`. Migration đã áp: `kho_san_pham 0009`, `san_xuat 0085`, `0086`. Trạng thái
sau deploy:

| Kiểm | Kết quả |
|---|---|
| Kho | 2 kho: `XUONG-TP` (id 1), `CH-TRUNG-TAM` (id 2) |
| YCNTP cũ | `YCNTP-2026-FULL-001` đã nối `warehouse_id=1`, giữ `warehouse_code='kv:4'` làm dấu vết |
| Sổ kho | Rỗng — đúng, vì phiếu còn `draft` và chưa kiểm kê |
| Form chọn kho | Trả `XUONG-TP` (chỉ kho `portal` mới nhận nhập thành phẩm) |

`deploy.sh` có thêm bước 8e nạp danh sách kho. Lưu ý: bước 1 của deploy làm
`git reset --hard`, thay chính tệp đang chạy, nên **sửa `deploy.sh` chỉ có hiệu lực từ lần
deploy sau**. Git thay tệp bằng rename nên tiến trình đang chạy đọc trọn bản cũ — không có
nguy cơ script bị đọc lẫn nửa cũ nửa mới. Lần này bước 8e được chạy tay bù.

## 14. Tồn đầu kỳ — cách làm

`Product.qty_on_hand` là cột trên danh mục để **xem và nhập** tồn xưởng. Nó không thay sổ
kho: sửa trên form/Excel gọi `set_catalog_qty` → `post_movement(kind=adjust)` vào
`XUONG-TP`, rồi cột danh mục được ghi lại từ tổng tồn các kho Portal. Bán hàng ở chi nhánh
không đổi số này.

Nhập từng SKU trên form Sửa sản phẩm, hoặc hàng loạt bằng Excel (cột `Tồn kho`).

Tồn đầu kỳ **phải đếm thực tế**, không bốc từ KiotViet sang. Tồn KiotViet đang mang sẵn sai
số tích lũy nhiều năm; nhập nó vào là kế thừa nguyên vẹn sai số đó rồi mất luôn khả năng
phân biệt "lệch do lịch sử" với "lệch do hệ mới ghi sai". Với chỉ 1 phiếu nhập thành phẩm
trong lịch sử, ở đây gần như không có gì để kế thừa — thời điểm tốt nhất để bắt đầu sổ sạch.

Phần đếm là việc nghiệp vụ. Phần nhập số đã có công cụ:
`kho_san_pham/management/commands/kho_sp_import_stocktake.py`.

Mẫu tệp: [stocktake-template.csv](./stocktake-template.csv) — hai cột `sku_code` và
`qty_counted`, cột khác bỏ qua. Lấy danh sách SKU để đếm:

```sql
SELECT code, name, color_label, size_label FROM kho_sp_product
WHERE is_active AND product_type = 'thanh_pham' ORDER BY code;
```

Chạy xem trước rồi mới ghi:

```bash
docker compose exec web python manage.py kho_sp_import_stocktake \
  --warehouse XUONG-TP --file /app/kk.csv
docker compose exec web python manage.py kho_sp_import_stocktake \
  --warehouse XUONG-TP --file /app/kk.csv --apply
```

Ba điểm đáng biết về cách lệnh này hoạt động:

- Nó ghi **chênh lệch** giữa số đếm và số sổ, không ghi đè. Nên dùng được cả cho tồn đầu kỳ
  (sổ đang trống) và kiểm kê định kỳ về sau.
- Chạy lại cùng tệp là vô hiệu, vì sau lần đầu sổ đã khớp số đếm nên chênh lệch bằng 0.
  An toàn hơn là dựa vào khóa chống trùng.
- Khóa chống trùng dùng **id sản phẩm** làm `source_line_no`, không phải số dòng trong tệp —
  sắp xếp lại tệp rồi chạy lại thì vẫn nhận ra là cùng một dòng.

SKU có trong tệp mà không có trong danh mục thì lệnh **dừng**, không ghi gì. Tồn đầu kỳ nhập
thiếu thì sai ngay từ gốc; muốn cố ý bỏ thì thêm `--skip-unknown`.

Mỗi phiếu kiểm kê chỉ cho **một kho** — số phiếu mặc định `KK-<ngày>-<mã kho>`. Vì khóa
chống trùng không có cột kho, gộp hai kho vào một số phiếu sẽ đụng khóa ở SKU nào có mặt ở
cả hai.

## 13. Danh sách kho — đã chốt 20/08/2026

Tra `kv_branch` thì toàn hệ chỉ có 2 địa điểm, cả hai đều trống `branch_code`. Đã chốt nạp
`Warehouse` như sau (nguồn: `kho_san_pham.choices.DEFAULT_WAREHOUSES`):

| `code` | `name` | `owner_system` | Vai trò |
|---|---|---|---|
| `XUONG-TP` | Kho thành phẩm — Xưởng sản xuất | `portal` | Nhận `production_in` từ `san_xuat` |
| `CH-TRUNG-TAM` | Chi nhánh trung tâm | `sales` | Bán hàng, nhận `sale_out` |

Xưởng dùng **một kho duy nhất** — không tách "kho thành phẩm" với "kho chờ xuất". Nếu sau
này cần tách thì phải chia lại số dư đang có, nên đây là chỗ đáng xem lại trước khi tồn
tích lũy nhiều.

Danh sách kho giờ do Portal quản, không còn đọc từ chi nhánh KiotViet:
`fg_warehouse_choices` trả mã kho thật (`XUONG-TP`) thay cho `kv:<pk>`. Đây là một mảng
nữa cắt được khỏi KiotViet — con số id chi nhánh sẽ hết nghĩa khi bỏ hẳn KiotViet.

### Hai kho — chỗ hiện và ai được ghi

| | `XUONG-TP` | `CH-TRUNG-TAM` |
|---|---|---|
| `owner_system` | `portal` | `sales` |
| Vai trò | Thành phẩm tại xưởng | Tồn điểm bán |
| Cột Tồn kho trên danh mục | **Có** — `Product.qty_on_hand` | **Không** — lọc `owner=portal` |
| Form / Excel "Tồn kho" | Ghi `adjust` vào kho này | Không sửa tay trên form danh mục |
| Nhập từ sản xuất | `production_in` — bắt buộc kho portal | Cấm |
| Bán / trả | Cấm | `sale_out` / `sale_return_in` |
| Chuyển kho | `transfer_out` | `transfer_in` |
| Tồn đầu kỳ | Đếm tại xưởng | 0 đến khi cắt KV; rồi đếm tại cửa hàng |
| Map KV | Chi nhánh xưởng (`kv:4`) | Chi nhánh trung tâm |

KiotViet còn tồn ở vài chi nhánh phụ — **không** tạo kho Portal cho chúng. Tra ở
module KiotViet. Chỉ hai địa điểm vật lý được chốt: xưởng và cửa hàng trung tâm.

Luồng: sản xuất → `XUONG-TP` (cột danh mục tăng) → phiếu chuyển → `CH-TRUNG-TAM`
→ bán trừ cửa hàng. Không trừ tồn xưởng khi bán.
