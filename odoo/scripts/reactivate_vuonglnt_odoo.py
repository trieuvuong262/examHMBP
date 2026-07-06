# flake8: noqa
"""Kích hoạt lại Vuonglnt trên Odoo và gán nhóm chuẩn."""
User = env['res.users'].sudo()
LOGIN = 'Vuonglnt'

u = User.browse(13)
if not u.exists():
    u = User.search([('login', '=', LOGIN)], limit=1)
if not u:
    u = User.with_context(active_test=False).search([('login', '=', LOGIN)], limit=1)
if not u:
    raise SystemExit(f'Không tìm thấy Odoo user {LOGIN!r}')

group_xml_ids = [
    'base.group_user',
    'stock.group_stock_user',
    'mrp.group_mrp_user',
    'stock.group_stock_manager',
    'mrp.group_mrp_manager',
]
group_ids = []
for xml_id in group_xml_ids:
    rec = env.ref(xml_id, raise_if_not_found=False)
    if rec:
        group_ids.append(rec.id)

vals = {
    'active': True,
    'name': 'LÊ NGUYỄN TRIỀU VƯƠNG',
    'email': 'vuonglnt@justplay.local',
    'groups_id': [(6, 0, group_ids)] if group_ids else False,
}
u.write(vals)
env.cr.commit()
print(f'OK odoo id={u.id} login={u.login!r} active={u.active} groups={len(u.groups_id)}')
