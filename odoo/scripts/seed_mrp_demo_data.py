#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dữ liệu demo Sản xuất (MRP) — JustPlay xưởng may.
Chạy trên VPS:
  docker compose -f /opt/odoo/docker-compose.yml exec -T odoo \
    odoo shell -d justplay_pilot --no-http -c /etc/odoo/odoo.conf \
    < /opt/odoo/scripts/seed_mrp_demo_data.py

Idempotent: bỏ qua nếu đã có sản phẩm JP-DEMO-TP-001.
"""
# flake8: noqa — odoo shell injects `env`

DEMO_TAG = 'JP-DEMO'
FINISHED_CODE = 'JP-DEMO-TP-001'


def _get_uom(xmlid, fallback_name=None):
    try:
        return env.ref(xmlid)
    except Exception:
        if fallback_name:
            return env['uom.uom'].search([('name', '=', fallback_name)], limit=1)
        raise


def _product(code, name, *, uom, categ_name='All', is_finished=False, list_price=0):
    Product = env['product.product']
    existing = Product.search([('default_code', '=', code)], limit=1)
    if existing:
        return existing
    categ = env['product.category'].search([('name', '=', categ_name)], limit=1)
    if not categ:
        categ = env['product.category'].create({'name': categ_name})
    vals = {
        'name': name,
        'default_code': code,
        'type': 'consu',
        'is_storable': True,
        'uom_id': uom.id,
        'uom_po_id': uom.id,
        'categ_id': categ.id,
        'list_price': list_price,
    }
    if is_finished:
        vals['route_ids'] = [(6, 0, [env.ref('mrp.route_warehouse0_manufacture').id])]
    return Product.create(vals)


def _workcenter(code, name):
    WC = env['mrp.workcenter']
    wc = WC.search([('code', '=', code)], limit=1)
    if wc:
        return wc
    return WC.create({
        'name': name,
        'code': code,
        'time_efficiency': 100,
        'costs_hour': 45000 if 'Cắt' in name else 35000,
    })


def _set_stock(product, qty, location):
    env['stock.quant'].with_context(inventory_mode=True).create({
        'product_id': product.id,
        'location_id': location.id,
        'inventory_quantity': qty,
    }).action_apply_inventory()


def seed():
    if not env['ir.module.module'].search([('name', '=', 'mrp'), ('state', '=', 'installed')], limit=1):
        print('ERROR: module mrp chưa cài')
        return False

    if env['product.product'].search([('default_code', '=', FINISHED_CODE)], limit=1):
        print(f'Đã có dữ liệu demo ({FINISHED_CODE}) — bỏ qua.')
        _summary()
        return True

    uom_unit = _get_uom('uom.product_uom_unit')
    uom_meter = _get_uom('uom.product_uom_meter')
    uom_kg = env['uom.uom'].search([('name', 'in', ['kg', 'Kilogram', 'kilogram'])], limit=1) or uom_unit

    wh = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
    stock_loc = wh.lot_stock_id

    # --- Work centers ---
    wc_cut = _workcenter('WC-CUT', 'Tổ cắt')
    wc_sew1 = _workcenter('WC-SEW1', 'Chuyền may 1')
    wc_sew2 = _workcenter('WC-SEW2', 'Chuyền may 2')
    wc_fin = _workcenter('WC-FIN', 'Hoàn thiện — ủi đóng gói')

    # --- Nguyên liệu ---
    p_fabric = _product(
        'JP-DEMO-NPL-001',
        'Vải cotton đỏ 180gsm',
        uom=uom_meter,
        categ_name='Nguyên liệu',
    )
    p_thread = _product(
        'JP-DEMO-NPL-002',
        'Chỉ may polyester đỏ',
        uom=uom_unit,
        categ_name='Nguyên liệu',
    )
    p_label = _product(
        'JP-DEMO-NPL-003',
        'Nhãn mác JustPlay',
        uom=uom_unit,
        categ_name='Nguyên liệu',
    )
    p_zipper = _product(
        'JP-DEMO-NPL-004',
        'Dây kéo zipper 20cm',
        uom=uom_unit,
        categ_name='Nguyên liệu',
    )

    # --- Thành phẩm ---
    p_shirt = _product(
        FINISHED_CODE,
        'Áo thun JustPlay đỏ — size M',
        uom=uom_unit,
        categ_name='Thành phẩm',
        is_finished=True,
        list_price=189000,
    )

    # --- BOM ---
    Bom = env['mrp.bom']
    bom = Bom.search([('product_id', '=', p_shirt.id)], limit=1)
    if not bom:
        bom = Bom.create({
            'product_tmpl_id': p_shirt.product_tmpl_id.id,
            'product_id': p_shirt.id,
            'product_qty': 1,
            'product_uom_id': uom_unit.id,
            'type': 'normal',
            'bom_line_ids': [
                (0, 0, {'product_id': p_fabric.id, 'product_qty': 1.2, 'product_uom_id': uom_meter.id}),
                (0, 0, {'product_id': p_thread.id, 'product_qty': 1, 'product_uom_id': uom_unit.id}),
                (0, 0, {'product_id': p_label.id, 'product_qty': 1, 'product_uom_id': uom_unit.id}),
                (0, 0, {'product_id': p_zipper.id, 'product_qty': 1, 'product_uom_id': uom_unit.id}),
            ],
            'operation_ids': [
                (0, 0, {'name': 'Cắt vải theo rập', 'workcenter_id': wc_cut.id, 'time_cycle': 3, 'sequence': 1}),
                (0, 0, {'name': 'May thân áo', 'workcenter_id': wc_sew1.id, 'time_cycle': 8, 'sequence': 2}),
                (0, 0, {'name': 'Overlock viền tay/cổ', 'workcenter_id': wc_sew2.id, 'time_cycle': 5, 'sequence': 3}),
                (0, 0, {'name': 'Ủi — đóng gói', 'workcenter_id': wc_fin.id, 'time_cycle': 4, 'sequence': 4}),
            ],
        })

    # --- Tồn kho NVL (đủ ~300 áo) ---
    _set_stock(p_fabric, 400, stock_loc)
    _set_stock(p_thread, 350, stock_loc)
    _set_stock(p_label, 350, stock_loc)
    _set_stock(p_zipper, 350, stock_loc)

    # --- Lệnh sản xuất demo ---
    MO = env['mrp.production']
    mo_specs = [
        ('JP-DEMO-MO-DRAFT', 80, False, False),
        ('JP-DEMO-MO-PLAN', 120, True, False),
        ('JP-DEMO-MO-WIP', 60, True, True),
    ]
    for ref, qty, confirm, start in mo_specs:
        if MO.search([('origin', '=', ref)], limit=1):
            continue
        mo = MO.create({
            'origin': ref,
            'product_id': p_shirt.id,
            'product_qty': qty,
            'product_uom_id': uom_unit.id,
            'bom_id': bom.id,
        })
        if confirm:
            mo.action_confirm()
        if start and mo.state in ('confirmed', 'progress'):
            mo.action_start()
            # Bắt đầu công đoạn đầu tiên nếu có workorder
            for wo in mo.workorder_ids[:1]:
                wo.button_start()

    env.cr.commit()
    print('==> Đã tạo dữ liệu demo MRP JustPlay')
    _summary()
    return True


def _summary():
    print('--- Tổng kết ---')
    print('Sản phẩm:', env['product.product'].search_count([('default_code', 'like', f'{DEMO_TAG}%')]))
    print('BOM:', env['mrp.bom'].search_count([]))
    print('Work center:', env['mrp.workcenter'].search_count([]))
    for mo in env['mrp.production'].search([('origin', 'like', f'{DEMO_TAG}%')], order='id'):
        print(f'  · {mo.name or mo.origin} | {mo.product_id.default_code} | qty={mo.product_qty} | {mo.state}')


seed()
