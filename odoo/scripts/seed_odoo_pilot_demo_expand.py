#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mở rộng demo Odoo pilot — thêm SP, tồn, đối tác, PO, LSX, bảo trì, hóa đơn.
Chạy sau seed_mrp / seed_stock / seed_odoo_pilot_demo (có thể chạy nhiều lần).
"""
# flake8: noqa

from datetime import timedelta

from odoo import fields

EXPAND_MARKER = 'justplay.odoo_pilot_demo_v2'
TAG = 'JP-DEMO'


def _installed(name):
    return bool(env['ir.module.module'].search([('name', '=', name), ('state', '=', 'installed')], limit=1))


def _get_uom(xmlid):
    return env.ref(xmlid)


def _categ(name):
    c = env['product.category'].search([('name', '=', name)], limit=1)
    return c or env['product.category'].create({'name': name})


def _product(code, name, *, uom, categ_name, list_price=0, standard_price=0, is_finished=False):
    Product = env['product.product']
    p = Product.search([('default_code', '=', code)], limit=1)
    if p:
        return p
    vals = {
        'name': name,
        'default_code': code,
        'type': 'consu',
        'is_storable': True,
        'uom_id': uom.id,
        'uom_po_id': uom.id,
        'categ_id': _categ(categ_name).id,
        'list_price': list_price,
        'standard_price': standard_price,
    }
    if is_finished and _installed('mrp'):
        vals['route_ids'] = [(6, 0, [env.ref('mrp.route_warehouse0_manufacture').id])]
    return Product.create(vals)


def _partner(ref, name, **extra):
    p = env['res.partner'].search([('ref', '=', ref)], limit=1)
    if p:
        return p
    return env['res.partner'].create({'name': name, 'ref': ref, 'company_type': 'company', **extra})


def _set_stock(product, qty, location):
    Quant = env['stock.quant'].with_context(inventory_mode=True)
    q = Quant.search([('product_id', '=', product.id), ('location_id', '=', location.id)], limit=1)
    if q:
        q.write({'inventory_quantity': qty})
        q.action_apply_inventory()
    else:
        Quant.create({
            'product_id': product.id,
            'location_id': location.id,
            'inventory_quantity': qty,
        }).action_apply_inventory()


def seed_products_and_stock():
    uom_unit = _get_uom('uom.product_uom_unit')
    uom_meter = _get_uom('uom.product_uom_meter')
    wh = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
    loc = wh.lot_stock_id

    catalog = [
        ('JP-DEMO-NPL-010', 'Vải cotton xanh navy 180gsm', uom_meter, 'Nguyên liệu', 0, 86000),
        ('JP-DEMO-NPL-011', 'Vải thun 2 chiều ghi', uom_meter, 'Nguyên liệu', 0, 79000),
        ('JP-DEMO-NPL-012', 'Dây thun lưng 3cm', uom_meter, 'Nguyên liệu', 0, 12000),
        ('JP-DEMO-NPL-013', 'Keo dán nhãn', uom_unit, 'Nguyên liệu', 0, 35000),
        ('JP-DEMO-NPL-014', 'Mực in logo JustPlay', uom_unit, 'Nguyên liệu', 0, 280000),
        ('JP-DEMO-NPL-015', 'Bao thơm chống ẩm', uom_unit, 'Bao bì', 0, 2500),
        ('JP-DEMO-TP-005', 'Áo thun JustPlay navy — size M', uom_unit, 'Thành phẩm', 199000, 92000, True),
        ('JP-DEMO-TP-006', 'Áo thun JustPlay ghi — size L', uom_unit, 'Thành phẩm', 189000, 88000, True),
        ('JP-DEMO-TP-007', 'Áo thun JustPlay đỏ — size XL', uom_unit, 'Thành phẩm', 209000, 98000, True),
        ('JP-DEMO-TP-008', 'Áo thun JustPlay trắng — size S', uom_unit, 'Thành phẩm', 179000, 85000, True),
        ('JP-DEMO-TP-009', 'Áo polo JustPlay đỏ — size M', uom_unit, 'Thành phẩm', 259000, 125000, True),
        ('JP-DEMO-TP-010', 'Áo polo JustPlay đen — size L', uom_unit, 'Thành phẩm', 269000, 130000, True),
    ]
    new_p = 0
    for row in catalog:
        code, name, uom, categ, lp, cost = row[:6]
        is_fin = len(row) > 6 and row[6] is True
        existed = bool(env['product.product'].search([('default_code', '=', code)], limit=1))
        _product(code, name, uom=uom, categ_name=categ, list_price=lp, standard_price=cost, is_finished=is_fin)
        if not existed:
            new_p += 1

    # Tăng tồn toàn bộ dòng JP-DEMO (cũ + mới)
    targets = {
        'JP-DEMO-NPL-001': 1200, 'JP-DEMO-NPL-002': 900, 'JP-DEMO-NPL-003': 850, 'JP-DEMO-NPL-004': 780,
        'JP-DEMO-NPL-005': 720, 'JP-DEMO-NPL-006': 680, 'JP-DEMO-NPL-007': 3800, 'JP-DEMO-NPL-008': 2200,
        'JP-DEMO-NPL-009': 320, 'JP-DEMO-NPL-010': 450, 'JP-DEMO-NPL-011': 390, 'JP-DEMO-NPL-012': 2800,
        'JP-DEMO-NPL-013': 180, 'JP-DEMO-NPL-014': 45, 'JP-DEMO-NPL-015': 600,
        'JP-DEMO-TP-001': 180, 'JP-DEMO-TP-002': 220, 'JP-DEMO-TP-003': 165, 'JP-DEMO-TP-004': 120,
        'JP-DEMO-TP-005': 95, 'JP-DEMO-TP-006': 110, 'JP-DEMO-TP-007': 88, 'JP-DEMO-TP-008': 140,
        'JP-DEMO-TP-009': 75, 'JP-DEMO-TP-010': 68,
    }
    for code, qty in targets.items():
        p = env['product.product'].search([('default_code', '=', code)], limit=1)
        if p:
            _set_stock(p, qty, loc)
    print(f'  Sản phẩm mới: {new_p} | Tồn cập nhật: {len(targets)}')


def seed_partners():
    suppliers = [
        ('JP-DEMO-SUP-004', 'Dệt may Đông Phương', {'supplier_rank': 1}),
        ('JP-DEMO-SUP-005', 'In ấn Logo Pro', {'supplier_rank': 1}),
        ('JP-DEMO-SUP-006', 'Bao bì Bình Minh', {'supplier_rank': 1}),
    ]
    customers = [
        ('JP-DEMO-CUS-003', 'CH JustPlay Thủ Đức', {'customer_rank': 1}),
        ('JP-DEMO-CUS-004', 'Đại lý Fashion Hub', {'customer_rank': 1}),
        ('JP-DEMO-CUS-005', 'Sàn TMĐT — kho lẻ', {'customer_rank': 1}),
        ('JP-DEMO-CUS-006', 'Công ty CP May Xuất khẩu A', {'customer_rank': 1}),
    ]
    partners = {}
    for ref, name, kw in suppliers + customers:
        partners[ref] = _partner(ref, name, **kw)
    print(f'  Đối tác thêm: {len(suppliers)} NCC + {len(customers)} KH')
    return partners


def _all_partners():
    return {p.ref: p for p in env['res.partner'].search([('ref', 'like', f'{TAG}-%')]) if p.ref}


def seed_purchase(partners):
    if not _installed('purchase'):
        return
    PO = env['purchase.order']
    lines_batch = [
        ('JP-DEMO-PO-004', 'JP-DEMO-SUP-004', [
            ('JP-DEMO-NPL-010', 300, 85500),
            ('JP-DEMO-NPL-011', 250, 78500),
        ], True),
        ('JP-DEMO-PO-005', 'JP-DEMO-SUP-005', [
            ('JP-DEMO-NPL-014', 20, 275000),
            ('JP-DEMO-NPL-003', 800, 820),
        ], True),
        ('JP-DEMO-PO-006', 'JP-DEMO-SUP-006', [
            ('JP-DEMO-NPL-008', 1500, 430),
            ('JP-DEMO-NPL-015', 400, 2400),
        ], False),
        ('JP-DEMO-PO-007', 'JP-DEMO-SUP-001', [
            ('JP-DEMO-NPL-001', 400, 81500),
            ('JP-DEMO-NPL-002', 350, 18000),
        ], True),
        ('JP-DEMO-PO-008', 'JP-DEMO-SUP-002', [
            ('JP-DEMO-NPL-004', 600, 3200),
            ('JP-DEMO-NPL-012', 500, 11500),
        ], True),
        ('JP-DEMO-PO-009', 'JP-DEMO-SUP-003', [
            ('JP-DEMO-NPL-013', 50, 34000),
        ], False),
        ('JP-DEMO-PO-010', 'JP-DEMO-SUP-004', [
            ('JP-DEMO-NPL-006', 200, 81800),
        ], True),
    ]
    created = 0
    all_p = {**_all_partners(), **partners}
    for origin, sup_ref, lines, confirm in lines_batch:
        if PO.search([('origin', '=', origin)], limit=1):
            continue
        partner = all_p.get(sup_ref)
        if not partner:
            continue
        order_lines = []
        for prod_code, qty, price in lines:
            product = env['product.product'].search([('default_code', '=', prod_code)], limit=1)
            if not product:
                continue
            order_lines.append((0, 0, {
                'product_id': product.id,
                'product_qty': qty,
                'price_unit': price,
                'product_uom': product.uom_id.id,
            }))
        if not order_lines:
            continue
        po = PO.create({'partner_id': partner.id, 'origin': origin, 'order_line': order_lines})
        created += 1
        if confirm:
            po.button_confirm()
    print(f'  Đơn mua thêm: +{created}')


def seed_mrp_extra():
    if not _installed('mrp'):
        return
    uom_unit = _get_uom('uom.product_uom_unit')
    uom_meter = _get_uom('uom.product_uom_meter')
    MO = env['mrp.production']
    Bom = env['mrp.bom']

    def _bom_for(finished_code, component_lines):
        fp = env['product.product'].search([('default_code', '=', finished_code)], limit=1)
        if not fp:
            return None
        bom = Bom.search([('product_id', '=', fp.id)], limit=1)
        if bom:
            return bom
        bl = []
        for comp_code, qty, uom in component_lines:
            cp = env['product.product'].search([('default_code', '=', comp_code)], limit=1)
            if cp:
                bl.append((0, 0, {'product_id': cp.id, 'product_qty': qty, 'product_uom_id': uom.id}))
        if not bl:
            return None
        return Bom.create({
            'product_tmpl_id': fp.product_tmpl_id.id,
            'product_id': fp.id,
            'product_qty': 1,
            'product_uom_id': uom_unit.id,
            'bom_line_ids': bl,
        })

    _bom_for('JP-DEMO-TP-005', [
        ('JP-DEMO-NPL-010', 1.2, uom_meter),
        ('JP-DEMO-NPL-002', 1, uom_unit),
        ('JP-DEMO-NPL-003', 1, uom_unit),
    ])
    _bom_for('JP-DEMO-TP-002', [
        ('JP-DEMO-NPL-005', 1.2, uom_meter),
        ('JP-DEMO-NPL-002', 1, uom_unit),
        ('JP-DEMO-NPL-003', 1, uom_unit),
        ('JP-DEMO-NPL-004', 1, uom_unit),
    ])
    _bom_for('JP-DEMO-TP-003', [
        ('JP-DEMO-NPL-006', 1.2, uom_meter),
        ('JP-DEMO-NPL-002', 1, uom_unit),
        ('JP-DEMO-NPL-003', 1, uom_unit),
    ])
    _bom_for('JP-DEMO-TP-007', [
        ('JP-DEMO-NPL-001', 1.3, uom_meter),
        ('JP-DEMO-NPL-002', 1, uom_unit),
        ('JP-DEMO-NPL-003', 1, uom_unit),
        ('JP-DEMO-NPL-004', 1, uom_unit),
    ])
    _bom_for('JP-DEMO-TP-009', [
        ('JP-DEMO-NPL-001', 1.4, uom_meter),
        ('JP-DEMO-NPL-002', 1, uom_unit),
        ('JP-DEMO-NPL-004', 1, uom_unit),
        ('JP-DEMO-NPL-003', 1, uom_unit),
    ])

    mo_batch = [
        ('JP-DEMO-MO-004', 'JP-DEMO-TP-002', 150, True, False),
        ('JP-DEMO-MO-005', 'JP-DEMO-TP-003', 100, True, True),
        ('JP-DEMO-MO-006', 'JP-DEMO-TP-005', 200, True, False),
        ('JP-DEMO-MO-007', 'JP-DEMO-TP-009', 80, False, False),
        ('JP-DEMO-MO-008', 'JP-DEMO-TP-001', 250, True, True),
        ('JP-DEMO-MO-009', 'JP-DEMO-TP-007', 90, True, False),
    ]
    created = 0
    for origin, prod_code, qty, confirm, start in mo_batch:
        if MO.search([('origin', '=', origin)], limit=1):
            continue
        product = env['product.product'].search([('default_code', '=', prod_code)], limit=1)
        if not product:
            continue
        bom = Bom.search([('product_id', '=', product.id)], limit=1)
        if not bom:
            continue
        mo = MO.create({
            'origin': origin,
            'product_id': product.id,
            'product_qty': qty,
            'product_uom_id': uom_unit.id,
            'bom_id': bom.id,
        })
        created += 1
        if confirm:
            mo.action_confirm()
        if start and mo.state in ('confirmed', 'progress'):
            mo.action_start()
            for wo in mo.workorder_ids[:1]:
                wo.button_start()
    print(f'  Lệnh SX thêm: +{created}')


def seed_maintenance_extra():
    if not _installed('maintenance'):
        return
    Cat = env['maintenance.equipment.category']
    cat_sew = Cat.search([('name', '=', 'Máy may JustPlay')], limit=1)
    cat_cut = Cat.search([('name', '=', 'Máy cắt & hoàn thiện')], limit=1)
    if not cat_cut:
        cat_cut = Cat.create({'name': 'Máy cắt & hoàn thiện'})

    Equip = env['maintenance.equipment']
    extra_eq = [
        ('Máy may Juki — Chuyền 1 máy 2', 'JK-DEMO-8700-02', cat_sew),
        ('Máy may Juki — Chuyền 1 máy 3', 'JK-DEMO-8700-03', cat_sew),
        ('Máy overlock — Chuyền 2 máy 2', 'PG-DEMO-M832-03', cat_sew),
        ('Máy thêu Tajima 2 đầu', 'TJ-DEMO-C1501-01', cat_sew),
        ('Bàn cắt tự động Gerber', 'GB-DEMO-XL-01', cat_cut),
        ('Máy đóng gói chân không', 'VC-DEMO-500-01', cat_cut),
    ]
    eq_count = 0
    for name, serial, cat in extra_eq:
        if not Equip.search([('serial_no', '=', serial)], limit=1):
            Equip.create({
                'name': name,
                'serial_no': serial,
                'category_id': cat.id,
                'partner_id': env.company.partner_id.id,
                'effective_date': fields.Date.today() - timedelta(days=200),
            })
            eq_count += 1

    Req = env['maintenance.request']
    requests = [
        ('JP-DEMO-MR-004', 'JK-DEMO-8700-02', 'preventive', 'Tra dầu — kiểm tra định kỳ', '1'),
        ('JP-DEMO-MR-005', 'JK-DEMO-8700-03', 'corrective', 'Gãy kim liên tục', '3'),
        ('JP-DEMO-MR-006', 'PG-DEMO-M832-03', 'corrective', 'Chỉ hay đứt chỉ trên', '2'),
        ('JP-DEMO-MR-007', 'TJ-DEMO-C1501-01', 'preventive', 'Vệ sinh đầu thêu', '1'),
        ('JP-DEMO-MR-008', 'GB-DEMO-XL-01', 'corrective', 'Lệch dao cắt 2mm', '2'),
        ('JP-DEMO-MR-009', 'VC-DEMO-500-01', 'preventive', 'Thay băng tải định kỳ', '1'),
        ('JP-DEMO-MR-010', 'JK-DEMO-8700-01', 'preventive', 'Kiểm tra motor chính', '1'),
        ('JP-DEMO-MR-011', 'EM-DEMO-625-03', 'corrective', 'Thay dao cắt mới', '3'),
    ]
    mr_created = 0
    for name, serial, mtype, desc, prio in requests:
        if Req.search([('name', '=', name)], limit=1):
            continue
        eq = Equip.search([('serial_no', '=', serial)], limit=1)
        if not eq:
            continue
        Req.create({
            'name': name,
            'equipment_id': eq.id,
            'maintenance_type': mtype,
            'description': desc,
            'priority': prio,
            'schedule_date': fields.Datetime.now() + timedelta(days=mr_created % 5),
        })
        mr_created += 1
    print(f'  Bảo trì: +{eq_count} TB, +{mr_created} YC')


def seed_accounting_extra(partners):
    if not _installed('account'):
        return
    Move = env['account.move']
    today = fields.Date.today()
    all_p = {**_all_partners(), **partners}
    specs = [
        ('JP-DEMO-BILL-003', 'in_invoice', 'JP-DEMO-SUP-004', 'JP-DEMO-NPL-010', 280, 85000),
        ('JP-DEMO-BILL-004', 'in_invoice', 'JP-DEMO-SUP-005', 'JP-DEMO-NPL-014', 15, 280000),
        ('JP-DEMO-BILL-005', 'in_invoice', 'JP-DEMO-SUP-006', 'JP-DEMO-NPL-008', 800, 420),
        ('JP-DEMO-BILL-006', 'in_invoice', 'JP-DEMO-SUP-001', 'JP-DEMO-NPL-005', 180, 83500),
        ('JP-DEMO-INV-002', 'out_invoice', 'JP-DEMO-CUS-002', 'JP-DEMO-TP-002', 60, 199000),
        ('JP-DEMO-INV-003', 'out_invoice', 'JP-DEMO-CUS-003', 'JP-DEMO-TP-003', 45, 189000),
        ('JP-DEMO-INV-004', 'out_invoice', 'JP-DEMO-CUS-004', 'JP-DEMO-TP-005', 35, 199000),
        ('JP-DEMO-INV-005', 'out_invoice', 'JP-DEMO-CUS-005', 'JP-DEMO-TP-001', 120, 189000),
        ('JP-DEMO-INV-006', 'out_invoice', 'JP-DEMO-CUS-006', 'JP-DEMO-TP-009', 25, 259000),
    ]
    created = 0
    for ref, mtype, pref, pcode, qty, price in specs:
        if Move.search([('ref', '=', ref)], limit=1):
            continue
        partner = all_p.get(pref)
        product = env['product.product'].search([('default_code', '=', pcode)], limit=1)
        if not partner or not product:
            continue
        move = Move.create({
            'move_type': mtype,
            'partner_id': partner.id,
            'ref': ref,
            'invoice_date': today - timedelta(days=created % 14),
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': product.display_name,
                'quantity': qty,
                'price_unit': price,
            })],
        })
        try:
            move.action_post()
        except Exception as exc:
            print(f'  Cảnh báo {ref}: {exc}')
        created += 1
    print(f'  Kế toán thêm: +{created}')


def _summary():
    print('--- Tổng kết sau mở rộng ---')
    for label, val in [
        ('Sản phẩm JP-DEMO', env['product.product'].search_count([('default_code', 'like', f'{TAG}%')])),
        ('NCC', env['res.partner'].search_count([('ref', 'like', f'{TAG}-SUP%')])),
        ('KH', env['res.partner'].search_count([('ref', 'like', f'{TAG}-CUS%')])),
        ('Đơn mua', env['purchase.order'].search_count([('origin', 'like', f'{TAG}%')])),
        ('Lệnh SX', env['mrp.production'].search_count([('origin', 'like', f'{TAG}%')])),
        ('Thiết bị BT', env['maintenance.equipment'].search_count([])),
        ('YC bảo trì', env['maintenance.request'].search_count([('name', 'like', f'{TAG}%')])),
        ('Hóa đơn', env['account.move'].search_count([('ref', 'like', f'{TAG}%')])),
        ('Phiếu kho', env['stock.picking'].search_count([])),
        ('Dòng tồn >0', env['stock.quant'].search_count([('quantity', '>', 0)])),
    ]:
        print(f'  {label}: {val}')


def seed():
    cur = env['ir.config_parameter'].sudo().get_param('justplay.odoo_pilot_demo')
    print('==> Mở rộng demo Odoo pilot (v2)')
    if cur == EXPAND_MARKER:
        print('Đã mở rộng trước đó — cập nhật lại tồn kho & bổ sung thiếu.')
    partners = seed_partners()
    seed_products_and_stock()
    seed_purchase(partners)
    seed_mrp_extra()
    seed_maintenance_extra()
    seed_accounting_extra(partners)
    env['ir.config_parameter'].sudo().set_param('justplay.odoo_pilot_demo', EXPAND_MARKER)
    env.cr.commit()
    print('==> Hoàn tất mở rộng')
    _summary()
    return True


seed()
