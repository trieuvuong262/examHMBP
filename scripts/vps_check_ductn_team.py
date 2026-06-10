from django.contrib.auth import get_user_model
from hrm.concurrent_positions import auto_managed_user_ids, get_manual_subordinate_users
from hrm.permissions import get_report_team_users

User = get_user_model()
d = User.objects.get(username='Ductn')
p = d.profile
print('manual M2M:', p.subordinates.filter(is_active=True).count())
print('auto_managed:', len(auto_managed_user_ids(d)))
print('manual_sub:', get_manual_subordinate_users(d).count())
print('report_team:', get_report_team_users(d).count())
for u in get_report_team_users(d)[:5]:
    print(' ', u.username)
