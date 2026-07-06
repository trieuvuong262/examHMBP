# flake8: noqa
ductn = env['res.users'].sudo().search([('login', '=ilike', 'ductn')], limit=1)
admin = env['res.users'].sudo().search([('login', '=', 'admin')], limit=1)
active = env['res.users'].sudo().search_count([('active', '=', True), ('share', '=', False)])
print(f'active_internal_users={active}')
if ductn:
    missing = set(admin.groups_id.ids) - set(ductn.groups_id.ids)
    print(f'Ductn id={ductn.id} groups={len(ductn.groups_id)} system={ductn.has_group("base.group_system")} missing_vs_admin={len(missing)}')
else:
    print('Ductn not found')
