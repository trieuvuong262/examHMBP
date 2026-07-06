# flake8: noqa
"""Nâng quyền Odoo user ductn ngang hàng administrator (admin).

Chạy trên VPS:
  docker exec -i odoo-web odoo shell -d justplay_pilot --no-http \\
    < /opt/odoo/scripts/upgrade_ductn_odoo_admin.py
"""
User = env['res.users'].sudo()

TARGET_LOGINS = ('Ductn', 'ductn')
ADMIN_LOGIN = 'admin'

admin = User.search([('login', '=', ADMIN_LOGIN)], limit=1)
if not admin:
    raise SystemExit(f'Không tìm thấy admin ({ADMIN_LOGIN})')

target = None
for login in TARGET_LOGINS:
    target = User.search([('login', '=', login)], limit=1)
    if target:
        break
if not target:
    raise SystemExit('Không tìm thấy user ductn/Ductn')

before_system = target._is_system()
before_groups = set(target.groups_id.ids)
admin_groups = list(admin.groups_id.ids)

print(f'Admin id={admin.id} login={admin.login!r} groups={len(admin_groups)}')
print(f'Target id={target.id} login={target.login!r} groups_before={len(before_groups)} is_system={before_system}')

target.write({'groups_id': [(6, 0, admin_groups)]})
env.cr.commit()

target = User.browse(target.id)
after_groups = set(target.groups_id.ids)
added = sorted(after_groups - before_groups)
removed = sorted(before_groups - after_groups)

print('--- Hoàn tất ---')
print(f'  login={target.login!r} is_system={target._is_system()} is_admin={target._is_admin()}')
print(f'  groups_after={len(after_groups)} added={len(added)} removed={len(removed)}')
if added:
    print('  + Thêm:')
    for gid in added:
        g = env['res.groups'].browse(gid)
        print(f'      [{gid}] {g.full_name or g.name}')
if removed:
    print('  - Gỡ:')
    for gid in removed:
        g = env['res.groups'].browse(gid)
        print(f'      [{gid}] {g.full_name or g.name}')
