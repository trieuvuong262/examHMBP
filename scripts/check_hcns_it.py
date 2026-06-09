from django.contrib.auth.models import User
from hrm.models import Division
from hrm.user_search import subordinate_candidate_queryset
from hrm.permissions import ROLE_DIVISION_HEAD

u = User.objects.get(username='Vuonglnt')
p = u.profile
print('div IT id=', p.division_id)
for d in Division.objects.filter(department_id=p.department_id):
    c = User.objects.filter(profile__division=d, profile__is_employed=True).count()
    print(' ', d.pk, d.name, 'emp=', c)

qs = subordinate_candidate_queryset(
    exclude_user_id=u.pk,
    manager_role=ROLE_DIVISION_HEAD,
    department_id=7,
    division_id=None,
)
print('TP SX candidates (dept 7):', qs.count())
