"""Chẩn đoán đồng bộ Portal / LDAP / Odoo — chạy: python manage.py shell < diag_portal_ldap_odoo.py"""
from django.contrib.auth.models import User

from audit.services.nas_ldap_sync import nas_ldap_configured, _ldap_connection, _ldap_base_dn, _skip_usernames
from audit.services.odoo_sync import user_has_odoo_portal_access, odoo_configured, _execute
from ldap3 import SUBTREE

employed = User.objects.filter(is_active=True, profile__is_employed=True).select_related('profile')
odoo_access = [u for u in employed if user_has_odoo_portal_access(u)]
no_odoo = [u for u in employed if not user_has_odoo_portal_access(u)]

print('=== Portal ===')
print(f'employed_active={employed.count()}')
print(f'with_odoo_menu={len(odoo_access)}')
print(f'without_odoo_menu={len(no_odoo)}')

ldap_uids = set()
if nas_ldap_configured():
    with _ldap_connection() as conn:
        conn.search(
            f'cn=users,{_ldap_base_dn()}',
            '(objectClass=posixAccount)',
            search_scope=SUBTREE,
            attributes=['uid'],
        )
        ldap_uids = {str(e.uid) for e in conn.entries if hasattr(e, 'uid')}
    print(f'\n=== LDAP ===')
    print(f'ldap_users={len(ldap_uids)}')
    missing_ldap = []
    for u in employed:
        uid = (u.username or '').strip()
        if uid.lower() in _skip_usernames():
            continue
        if uid not in ldap_uids:
            missing_ldap.append(uid)
    print(f'missing_in_ldap={len(missing_ldap)}')
    if missing_ldap[:15]:
        print('  sample:', ', '.join(missing_ldap[:15]))
else:
    print('\nLDAP not configured')

if odoo_configured():
    active_ids = _execute('res.users', 'search', [('active', '=', True), ('share', '=', False)])
    inactive_with_profile = []
    for u in employed:
        p = u.profile
        if p.odoo_user_id and p.odoo_user_id not in active_ids:
            inactive_with_profile.append(u.username)
    unsynced_odoo_access = [u.username for u in odoo_access if not u.profile.odoo_user_id]
    print(f'\n=== Odoo ===')
    print(f'active_internal={len(active_ids)}')
    print(f'odoo_access_but_no_odoo_user_id={len(unsynced_odoo_access)}')
    print(f'had_odoo_id_now_inactive={len(inactive_with_profile)}')
    if unsynced_odoo_access[:10]:
        print('  unsynced:', ', '.join(unsynced_odoo_access[:10]))
    if inactive_with_profile[:10]:
        print('  deactivated:', ', '.join(inactive_with_profile[:10]))

unsynced_pw = [
    u.username for u in odoo_access
    if not getattr(u.profile, 'odoo_password_synced', False)
]
print(f'\n=== Mật khẩu Odoo (local) chưa khớp Portal ===')
print(f'count={len(unsynced_pw)}')
if unsynced_pw[:15]:
    print('  users:', ', '.join(unsynced_pw[:15]))
