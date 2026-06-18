from django.contrib.auth import get_user_model
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_REPORTS

User = get_user_model()
for uname in ['nv.tb', 'tp.tb', 'Ductn']:
    u = User.objects.filter(username=uname).select_related('profile__permission_group').first()
    if not u:
        print(uname, 'NOT FOUND')
        continue
    print('===', uname, '===')
    pg = getattr(getattr(u, 'profile', None), 'permission_group', None)
    if pg:
        perms = pg.get_permissions()
        reports = perms.get(MODULE_REPORTS, {})
        menus = reports.get('menus', {})
        print('  group:', pg.name)
        print('  reports view:', reports.get('view'))
        print('  menu keys:', list(menus.keys()) if menus else '(module-level only)')
    else:
        print('  no permission group')
    for k in ['daily', 'daily_cn', 'daily_cn_detail', 'daily_vp', 'daily_vp_detail', 'weekly']:
        print(' ', k, user_can_access_menu(u, MODULE_REPORTS, k))
