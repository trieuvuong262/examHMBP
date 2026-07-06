# flake8: noqa
"""So sánh sâu admin vs Ductn — tìm quyền còn thiếu cho kích hoạt app."""
User = env['res.users'].sudo()
admin = User.search([('login', '=', 'admin')], limit=1)
ductn = User.search([('login', '=', 'Ductn')], limit=1)

def dump(u, label):
    print(f'\n===== {label} id={u.id} login={u.login!r} =====')
    print('active', u.active, 'share', u.share)
    print('_is_system', u._is_system(), '_is_admin', u._is_admin(), '_is_internal', u._is_internal())
    print('company_ids', u.company_ids.ids, 'company_id', u.company_id.id)
    print('partner_id', u.partner_id.id, 'partner active', u.partner_id.active)
    groups = u.groups_id.sorted(lambda g: g.full_name or g.name)
    print('groups', len(groups))
    for g in groups:
        print(f'  [{g.id}] {g.full_name or g.name}')

dump(admin, 'admin')
dump(ductn, 'Ductn')

admin_set = set(admin.groups_id.ids)
ductn_set = set(ductn.groups_id.ids)
print('\n===== ONLY on admin =====')
for gid in sorted(admin_set - ductn_set):
    g = env['res.groups'].browse(gid)
    print(f'  [{gid}] {g.full_name or g.name}')
print('\n===== ONLY on ductn =====')
for gid in sorted(ductn_set - admin_set):
    g = env['res.groups'].browse(gid)
    print(f'  [{gid}] {g.full_name or g.name}')

# implied groups from base.group_system
try:
    sys_g = env.ref('base.group_system')
    print('\n===== implied by group_system =====')
    print('implied_ids', sys_g.implied_ids.ids)
    missing_impl = set(sys_g.trans_implied_ids.ids) - ductn_set
    if missing_impl:
        print('ductn missing implied:', missing_impl)
except Exception as e:
    print('implied check error', e)
