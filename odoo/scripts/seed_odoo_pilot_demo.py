#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo đầy đủ cho các module Odoo pilot đã cài (MRP, Stock, Purchase, Maintenance, Account).
Chạy:
  docker compose -f /opt/odoo/docker-compose.yml exec -T odoo \
    odoo shell -d justplay_pilot --no-http -c /etc/odoo/odoo.conf \
    < /opt/odoo/scripts/seed_odoo_pilot_demo.py

Trước đó nên có MRP + tồn kho: seed_mrp_demo_data.py, seed_stock_demo_data.py
"""
# flake8: noqa

from datetime import timedelta

from odoo import fields

MARKER = 'justplay.odoo_pilot_demo_v1'  # v2: seed_odoo_pilot_demo_expand.py
TAG = 'JP-DEMO'


def _installed(name):
    return bool(env['ir.module.module'].search([('name', '=', name), ('state', '=', 'installed')], limit=1))


def _done():
    return env['ir.config_parameter'].sudo().get_param('justplay.odoo_pilot_demo') == MARKER


def _mark_done():
    env['ir.config_parameter'].sudo().set_param('justplay.odoo_pilot_demo', MARKER)


def _partner(ref, name, **extra):
    Partner = env['res.partner']
    p = Partner.search([('ref', '=', ref)], limit=1)
    if p:
        return p
    vals = {'name': name, 'ref': ref, 'company_type': 'company'}
    vals.update(extra)
    return Partner.create(vals)


def _product(code):
    return env['product.product'].search([('default_code', '=', code)], limit=1)


def seed_partners():
    suppliers = [
        ('JP-DEMO-SUP-001', 'Công ty TNHH Vải Việt', {'supplier_rank': 1, 'street': '12 Nguyễn Văn Linh, Q7, TP.HCM', 'phone': '028 1234 5678'}),
        ('JP-DEMO-SUP-002', 'Phụ liệu May Minh Phát', {'supplier_rank': 1, 'street': 'KCN Tân Bình, TP.HCM'}),
        ('JP-DEMO-SUP-003', 'Thiết bị Juki Việt Nam', {'supplier_rank': 1}),
    ]
    customers = [
        ('JP-DEMO-CUS-001', 'Cửa hàng JustPlay Quận 1', {'customer_rank': 1}),
        ('JP-DEMO-CUS-002', 'Đại lý Thời trang An Phát', {'customer_rank': 1}),
    ]
    out = {}
    for ref, name, kw in suppliers + customers:
        out[ref] = _partner(ref, name, **kw)
    print(f'  Đối tác: {len(suppliers)} NCC + {len(customers)} KH')
    return out


def seed_purchase(partners):
    if not _installed('purchase'):
        return
    PO = env['purchase.order']
    specs = [
        ('JP-DEMO-PO-DRAFT', 'JP-DEMO-SUP-001', 'JP-DEMO-NPL-001', 200, 82000, False),
        ('JP-DEMO-PO-OPEN', 'JP-DEMO-SUP-002', 'JP-DEMO-NPL-003', 500, 850, True),
        ('JP-DEMO-PO-RCV', 'JP-DEMO-SUP-001', 'JP-DEMO-NPL-005', 150, 84000, True),
    ]
    created = 0
    for origin, sup_ref, prod_code, qty, price, confirm in specs:
        if PO.search([('origin', '=', origin)], limit=1):
            continue
        product = _product(prod_code)
        if not product:
            print(f'  Bỏ qua PO {origin}: thiếu SP {prod_code}')
            continue
        po = PO.create({
            'partner_id': partners[sup_ref].id,
            'origin': origin,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_qty': qty,
                'price_unit': price,
                'product_uom': product.uom_id.id,
            })],
        })
        created += 1
        if confirm:
            po.button_confirm()
            if origin == 'JP-DEMO-PO-RCV' and po.picking_ids:
                for picking in po.picking_ids:
                    for move in picking.move_ids_without_package:
                        move.quantity = move.product_uom_qty
                    picking.button_validate()
    print(f'  Đơn mua: +{created}')


def seed_maintenance():
    if not _installed('maintenance'):
        return
    Cat = env['maintenance.equipment.category']
    cat = Cat.search([('name', '=', 'Máy may JustPlay')], limit=1)
    if not cat:
        cat = Cat.create({'name': 'Máy may JustPlay'})

    Equip = env['maintenance.equipment']
    equip_specs = [
        ('JP-DEMO-EQ-001', 'Máy may Juki DDL-8700 — Chuyền 1', 'JK-DEMO-8700-01', 'WC-SEW1'),
        ('JP-DEMO-EQ-002', 'Máy overlock Pegasus M832', 'PG-DEMO-M832-02', 'WC-SEW2'),
        ('JP-DEMO-EQ-003', 'Máy cắt dao rung Eastman', 'EM-DEMO-625-03', 'WC-CUT'),
        ('JP-DEMO-EQ-004', 'Bàn ủi hơi Veit — Hoàn thiện', 'VT-DEMO-9210-04', 'WC-FIN'),
    ]
    equips = []
    for ref, name, serial, wc_code in equip_specs:
        eq = Equip.search([('serial_no', '=', serial)], limit=1)
        if not eq:
            vals = {
                'name': name,
                'serial_no': serial,
                'category_id': cat.id,
                'partner_id': env.company.partner_id.id,
                'effective_date': fields.Date.today() - timedelta(days=400),
            }
            if _installed('mrp'):
                wc = env['mrp.workcenter'].search([('code', '=', wc_code)], limit=1)
                if wc and 'workcenter_id' in Equip._fields:
                    vals['workcenter_id'] = wc.id
            eq = Equip.create(vals)
        equips.append(eq)

    Req = env['maintenance.request']
    req_specs = [
        ('JP-DEMO-MR-001', 'JP-DEMO-EQ-003', 'corrective', 'Dao cắt kém — cần mài lại', '2'),
        ('JP-DEMO-MR-002', 'JP-DEMO-EQ-004', 'preventive', 'Bảo dưỡng van hơi định kỳ', '1'),
        ('JP-DEMO-MR-003', 'JP-DEMO-EQ-001', 'corrective', 'Tiếng kêu bất thường đầu máy', '3'),
    ]
    created = 0
    ref_map = {s[0]: s for s in equip_specs}
    for origin, eq_ref, mtype, desc, priority in req_specs:
        if Req.search([('name', '=', origin)], limit=1):
            continue
        spec = ref_map.get(eq_ref)
        if not spec:
            continue
        serial = spec[2]
        eq = Equip.search([('serial_no', '=', serial)], limit=1)
        if not eq:
            continue
        Req.create({
            'name': origin,
            'equipment_id': eq.id,
            'maintenance_type': mtype,
            'description': desc,
            'priority': priority,
            'schedule_date': fields.Datetime.now() + timedelta(days=2),
        })
        created += 1
    print(f'  Bảo trì: {len(equips)} thiết bị, +{created} yêu cầu')


def seed_accounting(partners):
    if not _installed('account'):
        return
    Move = env['account.move']
    today = fields.Date.today()
    specs = [
        ('JP-DEMO-BILL-001', 'in_invoice', 'JP-DEMO-SUP-001', 'JP-DEMO-NPL-001', 120, 82000),
        ('JP-DEMO-BILL-002', 'in_invoice', 'JP-DEMO-SUP-002', 'JP-DEMO-NPL-008', 300, 420),
        ('JP-DEMO-INV-001', 'out_invoice', 'JP-DEMO-CUS-001', 'JP-DEMO-TP-001', 40, 189000),
    ]
    created = 0
    for ref, move_type, partner_ref, prod_code, qty, price in specs:
        if Move.search([('ref', '=', ref)], limit=1):
            continue
        product = _product(prod_code)
        partner = partners.get(partner_ref)
        if not partner or not product:
            continue
        move = Move.create({
            'move_type': move_type,
            'partner_id': partner.id,
            'ref': ref,
            'invoice_date': today,
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
            print(f'  Cảnh báo hạch toán {ref}: {exc}')
        created += 1
    print(f'  Kế toán: +{created} chứng từ')


def _summary():
    print('--- Tổng kết pilot ---')
    rows = [
        ('Sản phẩm', env['product.product'].search_count([('default_code', 'like', f'{TAG}%')])),
        ('NCC', env['res.partner'].search_count([('ref', 'like', f'{TAG}-SUP%')])),
        ('KH', env['res.partner'].search_count([('ref', 'like', f'{TAG}-CUS%')])),
        ('Đơn mua', env['purchase.order'].search_count([('origin', 'like', f'{TAG}%')]) if _installed('purchase') else '—'),
        ('Lệnh SX', env['mrp.production'].search_count([('origin', 'like', f'{TAG}%')]) if _installed('mrp') else '—'),
        ('Thiết bị BT', env['maintenance.equipment'].search_count([]) if _installed('maintenance') else '—'),
        ('YC bảo trì', env['maintenance.request'].search_count([]) if _installed('maintenance') else '—'),
        ('Hóa đơn', env['account.move'].search_count([('ref', 'like', f'{TAG}%')]) if _installed('account') else '—'),
        ('Phiếu kho', env['stock.picking'].search_count([])),
    ]
    for k, v in rows:
        print(f'  {k}: {v}')


def seed():
    print('==> Seed demo Odoo pilot (module còn thiếu dữ liệu)')
    if _done():
        print(f'Đã chạy ({MARKER}) — chỉ in tổng kết.')
        _summary()
        return True

    partners = seed_partners()
    seed_purchase(partners)
    seed_maintenance()
    seed_accounting(partners)
    _mark_done()
    env.cr.commit()
    print('==> Hoàn tất')
    _summary()
    return True


seed()
