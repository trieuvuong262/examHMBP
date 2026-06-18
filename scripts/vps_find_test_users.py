from django.contrib.auth import get_user_model
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_REPORTS
from hrm.permissions import can_submit_daily_report, can_view_team_reports

User = get_user_model()
print('Workers with daily_cn + can_submit:')
n = 0
for u in User.objects.filter(is_active=True).select_related('profile__department', 'profile__permission_group'):
    if can_submit_daily_report(u) and user_can_access_menu(u, MODULE_REPORTS, 'daily_cn'):
        dept = getattr(getattr(u, 'profile', None), 'department', None)
        print(f'  {u.username} — {dept.name if dept else "?"}')
        n += 1
        if n >= 10:
            break
print('\nLeaders with daily_vp_detail + team:')
n = 0
for u in User.objects.filter(is_active=True).select_related('profile__department'):
    if can_view_team_reports(u) and user_can_access_menu(u, MODULE_REPORTS, 'daily_vp_detail'):
        dept = getattr(getattr(u, 'profile', None), 'department', None)
        print(f'  {u.username} — {dept.name if dept else "?"}')
        n += 1
        if n >= 10:
            break
