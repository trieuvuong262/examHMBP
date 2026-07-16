# Hub Sản xuất JustPlay trên Odoo (scaffold — phụ)

> **UX chính đã chuyển sang Portal.** Xem [`docs/san_xuat/hub-portal.md`](../san_xuat/hub-portal.md).

App Odoo `justplay_sx` vẫn có thể cài trên https://erp.justplay.vn/ để thử SO→KH→LSX demo, nhưng **không** dùng làm giao diện vận hành hàng ngày (khó dùng hơn Portal).

## SoT (không đổi)

| | |
|--|--|
| NPL nhập/xuất/kiểm kê | Portal `kho_npl` |
| Mirror danh mục + tồn | Odoo Inventory WH `NPL` (bridge) |
| Hub menu 9 mục | **Portal** `/san-xuat/` |

## Addon Odoo (tuỳ chọn)

- Path: `odoo/addons/justplay_sx/`
- Cài: `bash /opt/odoo/scripts/install_justplay_sx.sh`
- Giữ trên VPS; không uninstall trong đợt Portal hub.

## Bridge NPL

[`docs/integrations/npl-odoo-bridge.md`](../integrations/npl-odoo-bridge.md)
