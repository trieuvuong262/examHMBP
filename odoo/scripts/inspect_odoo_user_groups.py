# flake8: noqa
User = env['res.users'].sudo()

def show(label, login):
    u = User.search([('login', 'ilike', login)], limit=1)
    if not u:
        print(f'--- {label} ({login}): NOT FOUND ---')
        return None
    groups = u.groups_id.sorted(lambda g: g.full_name or g.name)
    print(f'--- {label}: id={u.id} login={u.login!r} name={u.name!r} active={u.active} ---')
    print(f'  is_system={u._is_system()} is_admin={u._is_admin()}')
    for g in groups:
        print(f'  - [{g.id}] {g.full_name or g.name}')
    return u

admin = show('admin', 'admin')
ductn = show('ductn', 'ductn')
if not ductn:
    ductn = show('ductn', 'Ductn')
