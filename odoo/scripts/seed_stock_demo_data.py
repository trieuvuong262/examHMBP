#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dữ liệu demo Tồn kho — bổ sung / cập nhật số lượng trên kho chính.
Chạy trên VPS:
  docker compose -f /opt/odoo/docker-compose.yml exec -T odoo \
    odoo shell -d justplay_pilot --no-http -c /etc/odoo/odoo.conf \
    < /opt/odoo/scripts/seed_stock_demo_data.py

Idempotent: tạo SP mới nếu chưa có; mỗi lần chạy đặt lại tồn theo bảng STOCK_TARGETS.
"""
# flake8: noqa — odoo shell injects `env`

DEMO_PREFIX = 'JP-DEMO'


def _get_uom(xmlid):
    return env.ref(xmlid)


def _categ(name):
    categ = env['product.category'].search([('name', '=', name)], limit=1)
    if not categ:
        categ = env['product.category'].create({'name': name})
    return categ


def _product(code, name, *, uom, categ_name, list_price=0, standard_price=0):
    Product = env['product.product']
    p = Product.search([('default_code', '=', code)], limit=1)
    if p:
        return p
    return Product.create({
        'name': name,
        'default_code': code,
        'type': 'consu',
        'is_storable': True,
        'uom_id': uom.id,
        'uom_po_id': uom.id,
        'categ_id': _categ(categ_name).id,
        'list_price': list_price,
        'standard_price': standard_price,
    })


def _set_stock_qty(product, qty, location):
    """Đặt tồn kho tuyệt đối tại location (điều chỉnh tồn)."""
    Quant = env['stock.quant'].with_context(inventory_mode=True)
    quant = Quant.search([
        ('product_id', '=', product.id),
        ('location_id', '=', location.id),
    ], limit=1)
    if quant:
        quant.write({'inventory_quantity': qty})
        quant.action_apply_inventory()
        return
    Quant.create({
        'product_id': product.id,
        'location_id': location.id,
        'inventory_quantity': qty,
    }).action_apply_inventory()


def seed():
    if not env['ir.module.module'].search([('name', '=', 'stock'), ('state', '=', 'installed')], limit=1):
        print('ERROR: module stock chưa cài')
        return False

    uom_unit = _get_uom('uom.product_uom_unit')
    uom_meter = _get_uom('uom.product_uom_meter')

    wh = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
    if not wh:
        print('ERROR: chưa có kho')
        return False
    stock_loc = wh.lot_stock_id

    # Sản phẩm bổ sung (nếu chưa có)
    extras = [
        ('JP-DEMO-NPL-005', 'Vải cotton đen 180gsm', uom_meter, 'Nguyên liệu', 0, 85000),
        ('JP-DEMO-NPL-006', 'Vải cotton trắng 180gsm', uom_meter, 'Nguyên liệu', 0, 82000),
        ('JP-DEMO-NPL-007', 'Nút nhựa 12mm — trắng', uom_unit, 'Nguyên liệu', 0, 120),
        ('JP-DEMO-NPL-008', 'Túi OPP đóng gói áo', uom_unit, 'Bao bì', 0, 450),
        ('JP-DEMO-NPL-009', 'Thùng carton 40×30×25cm', uom_unit, 'Bao bì', 0, 12000),
        ('JP-DEMO-TP-002', 'Áo thun JustPlay đen — size L', uom_unit, 'Thành phẩm', 199000, 95000),
        ('JP-DEMO-TP-003', 'Áo thun JustPlay trắng — size M', uom_unit, 'Thành phẩm', 189000, 90000),
        ('JP-DEMO-TP-004', 'Áo thun JustPlay đỏ — size S', uom_unit, 'Thành phẩm', 179000, 88000),
    ]
    products = {}
    created = 0
    for code, name, uom, categ, lp, cost in extras:
        existed = bool(env['product.product'].search([('default_code', '=', code)], limit=1))
        products[code] = _product(code, name, uom=uom, categ_name=categ, list_price=lp, standard_price=cost)
        if not existed:
            created += 1

    # Mục tiêu tồn kho (mã → số lượng) — gồm NVL cũ + mới + thành phẩm
    STOCK_TARGETS = {
        # Nguyên liệu chính (tăng tồn)
        'JP-DEMO-NPL-001': 850,   # vải đỏ m
        'JP-DEMO-NPL-002': 620,   # chỉ
        'JP-DEMO-NPL-003': 580,   # nhãn
        'JP-DEMO-NPL-004': 540,   # zipper
        'JP-DEMO-NPL-005': 520,
        'JP-DEMO-NPL-006': 480,
        'JP-DEMO-NPL-007': 2500,
        'JP-DEMO-NPL-008': 1200,
        'JP-DEMO-NPL-009': 180,
        # Thành phẩm sẵn kho
        'JP-DEMO-TP-001': 95,
        'JP-DEMO-TP-002': 142,
        'JP-DEMO-TP-003': 78,
        'JP-DEMO-TP-004': 56,
    }

    updated = 0
    missing = []
    for code, qty in STOCK_TARGETS.items():
        p = env['product.product'].search([('default_code', '=', code)], limit=1)
        if not p:
            missing.append(code)
            continue
        _set_stock_qty(p, qty, stock_loc)
        updated += 1

    env.cr.commit()
    print('==> Đã cập nhật tồn kho demo JustPlay')
    print(f'Sản phẩm mới: {created} | Dòng tồn cập nhật: {updated}')
    if missing:
        print('Chưa có SP (chạy seed_mrp_demo_data.py trước):', ', '.join(missing))
    print(f'Kho: {wh.name} / {stock_loc.display_name}')
    print('--- Tồn kho hiện tại ---')
    quants = env['stock.quant'].search([
        ('location_id', '=', stock_loc.id),
        ('quantity', '>', 0),
    ], order='product_id')
    for q in quants:
        code = q.product_id.default_code or '—'
        print(f'  · {code:20} {q.product_id.name[:36]:36} {q.quantity:>10.0f} {q.product_id.uom_id.name}')
    return True


seed()
