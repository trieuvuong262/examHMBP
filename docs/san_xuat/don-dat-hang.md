# Đơn đặt hàng (Portal SoT)

> Phân hệ `/san-xuat/don-hang/` — **SoT đơn SX trên Portal** (không còn redirect KiotViet).  
> Benchmark UI: [AMIS sale-order](https://demoamisapp.misa.vn/production/sale-order) — xem khảo sát cũ + capture `_amis_survey/`.  
> Help MISA (tham chiếu): [Đơn đặt hàng](https://helpamis.misa.vn/amis-san-xuat/kb/don-dat-hang/).

## 1. Vai trò

```text
Tạo tay ──► SxSalesOrder (nháp)
                  │ xác nhận
                  ▼
            Đã xác nhận ──► Nạp KHTT MTO ──► KHCT ──► LSX
                  │
                  └── Giá thành theo mã đơn
```

## 2. Model

| Model | Ý nghĩa |
|-------|---------|
| `SxSalesOrder` | Header: mã DH-YYYY-####, khách, ngày YC, hạn SX, confirm_status, source, kv_* |
| `SxSalesOrderLine` | Mã SP (kho SP), qty, scrap %, SL cần SX = qty×(1+scrap%) |
| `SxOverallPlanLine.sales_order` | FK khi nạp MTO |
| `SxProductionOrder.sales_order` | FK (gán khi có liên kết) |

## 3. URL

| Path | View |
|------|------|
| `/san-xuat/don-hang/` | List + lọc |
| `/san-xuat/don-hang/them/` | Tạo đơn |
| `/san-xuat/don-hang/<pk>/` | Chi tiết: xác nhận / từ chối / tạo KHTT MTO |

## 4. Liên kết chức năng

| Chức năng | Cách nối |
|-----------|----------|
| KHTT MTO | Panel nạp chọn ĐĐH `confirmed`; `load_mto_demand(sales_order_ids=…)` |
| Detail ĐĐH | Nút «Tạo KHTT MTO & nạp nhu cầu» |
| KHCT / LSX | Luồng Portal giữ nguyên; detail ĐĐH liệt kê KHTT/LSX liên quan |
| Giá thành theo đơn | Link `?q=` mã ĐĐH |
| KiotViet | Không import vào ĐĐH (phase hiện tại) |

## 5. Phase 1 không làm

Tạm giữ NVL, đơn cha–con, Excel, thuê GC từ ĐĐH, kiểm NVL BOM popup, sync kế toán.

## 6. Code

- [`hub_models.py`](../../san_xuat/hub_models.py) — `SxSalesOrder*`
- [`services/sales_orders.py`](../../san_xuat/services/sales_orders.py)
- [`views_hub.py`](../../san_xuat/views_hub.py) — `sales_order_*`
- Templates: `sales_order_list/form/detail.html`
