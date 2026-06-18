from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_REPORTS, user_can_create_module
from hrm.permissions import can_submit_daily_report, can_view_team_reports, is_director, get_profile

User = get_user_model()
u = User.objects.filter(username='tp.tb').select_related('profile__permission_group').first()
if not u:
    print('tp.tb not found')
    raise SystemExit(1)

p = get_profile(u)
pg = p.permission_group if p else None
reports = (pg.get_permissions().get(MODULE_REPORTS, {}) if pg else {})

print('=== tp.tb ===')
print('role:', p.role if p else '?')
print('permission_group:', pg.name if pg else 'none')
print('reports module:', reports)
print('is_director:', is_director(u))
print('can_create_module(reports):', user_can_create_module(u, MODULE_REPORTS))
print('can_submit_daily_report:', can_submit_daily_report(u))
print('can_view_team_reports:', can_view_team_reports(u))
print('menu daily_cn:', user_can_access_menu(u, MODULE_REPORTS, 'daily_cn'))

c = Client(HTTP_HOST='portal.justplay.vn')
c.force_login(u)
for name in ['today_cn', 'team_cn', 'today']:
    r = c.get(reverse('reports:' + name))
    print(f'GET {name}: {r.status_code} -> {getattr(r, "url", "")}')
