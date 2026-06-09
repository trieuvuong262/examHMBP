from django.contrib.auth.models import User
from hrm.concurrent_positions import auto_managed_user_ids
from hrm.models import Department, Division
from hrm.permissions import get_report_team_users
from hrm.user_search import subordinate_candidate_queryset, visible_employed_profiles
from hrm.permissions import ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD

u = User.objects.get(username='Vuonglnt')
p = u.profile
print('Profile:', p.full_name, 'role=', p.role, 'dept=', p.department_id, p.department, 'div=', p.division_id, p.division)

it_div = Division.objects.filter(name__icontains='IT').first()
print('IT div:', it_div)
if it_div:
    vis = visible_employed_profiles(division_id=it_div.pk, department_id=p.department_id)
    print('visible IT employees:', vis.count(), list(vis.values_list('user__username', flat=True)[:10]))

auto = auto_managed_user_ids(u)
print('auto_managed count:', len(auto))
print('report team:', get_report_team_users(u).count())

qs_main = subordinate_candidate_queryset(
    exclude_user_id=u.pk,
    manager_role=p.role,
    department_id=p.department_id,
    division_id=p.division_id,
)
print('main subordinate candidates:', qs_main.count())

dept_sx = Department.objects.filter(name__icontains='SẢN').first() or Department.objects.filter(name__icontains='SX').first()
print('SX dept:', dept_sx)
if dept_sx:
    qs_slot = subordinate_candidate_queryset(
        exclude_user_id=u.pk,
        manager_role=ROLE_DEPARTMENT_HEAD,
        department_id=dept_sx.pk,
        division_id=None,
    )
    print('slot TP SX candidates:', qs_slot.count())
