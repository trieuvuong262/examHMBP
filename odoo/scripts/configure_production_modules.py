#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cấu hình Odoo pilot JustPlay — chỉ giữ app cần cho sản xuất.

Chạy trên VPS:
  docker exec -i odoo-web odoo shell -d justplay_pilot --no-http \\
    -c /etc/odoo/odoo.conf < /opt/odoo/scripts/configure_production_modules.py

Gỡ: POS, Project, CRM, Sales, Calendar (+ phụ thuộc).
Giữ / cài: stock, mrp, purchase, maintenance, portal addons.
"""
# flake8: noqa — odoo shell injects `env`

# Gỡ theo thứ tự: app phụ thuộc nhiều trước
APPS_TO_UNINSTALL = [
    'point_of_sale',
    'project_todo',
    'project',
    'sale_management',
    'crm',
    'calendar',
]

# App cần cho SX (Inventory + MRP + Mua hàng + Bảo trì máy xưởng)
APPS_TO_ENSURE = [
    'stock',
    'mrp',
    'purchase',
    'maintenance',
    'contacts',
    'portal_justplay_sso',
    'portal_justplay_brand',
]

# Bật biến thể sản phẩm (size/màu) nếu có stock
ENABLE_VARIANTS = True


def _state(name):
    mod = env['ir.module.module'].search([('name', '=', name)], limit=1)
    return mod.state if mod else 'missing'


def uninstall_apps():
    print('=== GỠ ỨNG DỤNG KHÔNG CẦN ===')
    for name in APPS_TO_UNINSTALL:
        mod = env['ir.module.module'].search([('name', '=', name)], limit=1)
        if not mod:
            print(f'  skip {name}: không có')
            continue
        if mod.state != 'installed':
            print(f'  skip {name}: state={mod.state}')
            continue
        print(f'  gỡ {name} ...')
        try:
            mod.button_immediate_uninstall()
            env.cr.commit()
            print(f'    OK')
        except Exception as exc:
            env.cr.rollback()
            print(f'    LỖI: {exc}')


def install_apps():
    print('=== CÀI / KÍCH HOẠT APP SX ===')
    for name in APPS_TO_ENSURE:
        mod = env['ir.module.module'].search([('name', '=', name)], limit=1)
        if not mod:
            print(f'  skip {name}: không tìm thấy module')
            continue
        if mod.state == 'installed':
            print(f'  OK {name}: đã cài')
            continue
        if mod.state == 'uninstalled':
            print(f'  cài {name} ...')
            try:
                mod.button_immediate_install()
                env.cr.commit()
                print(f'    OK')
            except Exception as exc:
                env.cr.rollback()
                print(f'    LỖI: {exc}')
        else:
            print(f'  {name}: state={mod.state}')


def enable_product_variants():
    if not ENABLE_VARIANTS:
        return
    print('=== BẬT BIẾN THỂ SẢN PHẨM ===')
    try:
        group = env.ref('product.group_product_variant', raise_if_not_found=False)
        if not group:
            print('  skip: product.group_product_variant không có')
            return
        users = env.ref('base.group_user')
        if group not in users.implied_ids:
            users.write({'implied_ids': [(4, group.id)]})
        # res.config.settings for persistence
        if 'res.config.settings' in env:
            Settings = env['res.config.settings']
            settings = Settings.create({})
            if hasattr(settings, 'group_product_variant'):
                settings.group_product_variant = True
                settings.execute()
            env.cr.commit()
        print('  OK')
    except Exception as exc:
        env.cr.rollback()
        print(f'  LỖI (có thể bật tay Inventory → Settings): {exc}')


def summary():
    print('=== TRẠNG THÁI SAU CẤU HÌNH ===')
    installed = env['ir.module.module'].search([('state', '=', 'installed')])
    apps = installed.filtered(lambda m: m.application)
    print('Applications (%d):' % len(apps))
    for name in sorted(apps.mapped('name')):
        print(' ', name)
    for name in APPS_TO_ENSURE:
        print(f'  {name}: {_state(name)}')


uninstall_apps()
install_apps()
enable_product_variants()
summary()
print('=== XONG ===')
