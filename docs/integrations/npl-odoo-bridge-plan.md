# Plan: Bridge NPL â†’ Odoo (Portal = SoT)

> Tráº¡ng thÃ¡i: **Ä‘Ã£ implement MVP** â€” xem [npl-odoo-bridge.md](./npl-odoo-bridge.md)

## Quyáº¿t Ä‘á»‹nh Ä‘Ã£ chá»‘t

- **Nguá»“n sá»± tháº­t:** Portal `kho_npl` â€” Ä‘á»“ng bá»™ **má»™t chiá»u** sang Odoo (cÃ¹ng mÃ´ hÃ¬nh `kiotviet/odoo_bridge.py`).
- **KhÃ³a idempotent:** `Material.code` == Odoo `product.product.default_code`.
- **KhÃ´ng** clone Django app; **khÃ´ng** dual-write trong MVP.

## Hiá»‡n tráº¡ng táº­n dá»¥ng

```text
kho_npl.Material + StockBalance
        â”‚
        â–¼
kho_npl/odoo_bridge.py  (má»›i â€” copy pattern tá»« kiotviet/odoo_bridge.py)
        â”‚  XML-RPC: audit.services.odoo_sync._execute
        â–¼
Odoo: product.category (root "Kho NPL")
      product.product (consu + is_storable)
      stock.warehouse NPL + locations
      stock.quant (tá»“n)
```

Tham chiáº¿u:

- Bridge KV: [`kiotviet/odoo_bridge.py`](../../kiotviet/odoo_bridge.py)
- CLI KV: [`kiotviet/management/commands/kiotviet_odoo_push.py`](../../kiotviet/management/commands/kiotviet_odoo_push.py)
- Demo NVL Odoo: [`odoo/scripts/seed_mrp_demo_data.py`](../../odoo/scripts/seed_mrp_demo_data.py) (`type=consu`, `is_storable=True`)

## Pháº¡m vi MVP

### 1. Push danh má»¥c NPL â†’ product

| Portal | Odoo |
|--------|------|
| `Material.code` | `default_code` |
| `Material.name` | `name` |
| `Material.category` | `product.category` dÆ°á»›i root **`Kho NPL`** (tÃ¡ch root `KiotViet`) |
| `Material.unit` | map `uom.uom` (báº£ng cá»‘ Ä‘á»‹nh; thiáº¿u â†’ Units + log) |
| `Material.base_price` / avg batch | `standard_price` |
| `Material.is_active` | `active` |
| â€” | `type=consu`, `is_storable=True`, `purchase_ok=True`, `sale_ok=False` |

### 2. Warehouse / location

- Warehouse Odoo code cá»‘ Ä‘á»‹nh: **`NPL`**.
- Map `WarehouseLocation.code` â†’ `stock.location` internal dÆ°á»›i Stock cá»§a warehouse Ä‘Ã³.
- Vá»‹ trÃ­ scrap Portal (`HUY`) â†’ location scrap náº¿u cÃ³.

### 3. Push tá»“n

- Nguá»“n: `StockBalance(material, location).quantity` â†’ `stock.quant` inventory mode.
- CLI máº·c Ä‘á»‹nh **dry-run**; ghi tháº­t cáº§n `--apply`.

### 4. Reconcile (chá»‰ Ä‘á»c)

- Missing in Odoo / duplicate codes / nameâ€“price mismatch / location chÆ°a map.
- Cáº£nh bÃ¡o náº¿u `Material.code` trÃ¹ng mÃ£ Ä‘Ã£ cÃ³ tá»« KiotViet hoáº·c `JP-DEMO-*`.

## NgoÃ i pháº¡m vi MVP (phase sau)

- Sync ngÆ°á»£c Odoo â†’ Portal
- `MaterialBatch` â†’ lot/serial
- Push tá»«ng phiáº¿u nháº­p/xuáº¥t (chá»‰ tá»“n tuyá»‡t Ä‘á»‘i)
- Cron/hook auto-push khi ghi sá»•
- `san_xuat` BomLine â†’ `mrp.bom` (lÃ m **sau** khi NVL Ä‘Ã£ cÃ³ trÃªn Odoo)

## File sáº½ táº¡o

| File | Vai trÃ² |
|------|---------|
| `kho_npl/odoo_bridge.py` | reconcile + ensure + push materials/stock |
| `kho_npl/management/commands/npl_odoo_reconcile.py` | Chá»‰ Ä‘á»c |
| `kho_npl/management/commands/npl_odoo_push.py` | `--apply`, `--limit`, `--no-stock`, `--codes` |
| `kho_npl/tests_odoo_bridge.py` | Unit map UoM / vals (mock `_execute`) |
| `docs/integrations/npl-odoo-bridge.md` | HÆ°á»›ng dáº«n váº­n hÃ nh (sau khi code) |

Cáº­p nháº­t: `docs/odoo18/pilot-demo-map.md` Â§8 (NPL sync).

## Thá»© tá»± implement

1. Scaffold `odoo_bridge` + `npl_odoo_reconcile` (khÃ´ng ghi).
2. `ensure_npl_category_tree` + `ensure_npl_warehouse` + map locations.
3. `push_materials` (dry-run â†’ apply thá»­ vÃ i mÃ£ `JP-VAI-*`).
4. `push_npl_stock` tá»« `StockBalance`.
5. Tests + docs + smoke trÃªn `justplay_pilot`.

## CLI dá»± kiáº¿n

```bash
# Chá»‰ Ä‘á»‘i chiáº¿u
python manage.py npl_odoo_reconcile

# Xem káº¿ hoáº¡ch (khÃ´ng ghi)
python manage.py npl_odoo_push --limit 20

# Ghi tháº­t danh má»¥c + tá»“n
python manage.py npl_odoo_push --apply --limit 20

# Chá»‰ danh má»¥c, khÃ´ng tá»“n
python manage.py npl_odoo_push --apply --no-stock
```

## TiÃªu chÃ­ xong

- [ ] Reconcile cháº¡y Ä‘Æ°á»£c, cÃ³ sá»‘ matched / missing.
- [ ] Push `--apply` táº¡o product NPL trÃªn Odoo; cháº¡y láº¡i khÃ´ng nhÃ¢n Ä‘Ã´i.
- [ ] Root category `Kho NPL` â‰  `KiotViet`.
- [ ] Tá»“n 1â€“2 location Portal khá»›p quant Odoo (sai sá»‘ lÃ m trÃ²n OK).
- [ ] CÃ³ thá»ƒ gáº¯n NVL vá»«a push lÃ m component BoM Odoo (pilot may / SP008073).

## LiÃªn há»‡ module SX trÃªn ERP

Sau bridge nÃ y:

1. Push / xÃ¡c nháº­n FG `SP008073` (bridge KiotViet Ä‘Ã£ cÃ³).
2. Táº¡o `mrp.bom` trÃªn Odoo: components = NVL vá»«a sync.
3. Táº¡o MO thá»­ â€” consume tá»“n NPL Odoo.

Portal `san_xuat` giá»¯ vai trÃ² máº«u Ä‘á»‹nh má»©c táº¡m; SoT BOM chuyá»ƒn dáº§n sang Odoo khi NVL á»•n Ä‘á»‹nh.

