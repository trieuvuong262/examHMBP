from django.contrib.auth.models import User
from hrm.models import ProfileConcurrentPosition, Department
from hrm.permissions import get_report_team_users, ROLE_DEPARTMENT_HEAD
from hrm.concurrent_positions import auto_managed_user_ids

u = User.objects.get(username='Vuonglnt')
p = u.profile
dept = Department.objects.get(pk=7)
slot, created = ProfileConcurrentPosition.objects.get_or_create(
    profile=p,
    department=dept,
    division=None,
    job_position='Trưởng phòng',
    defaults={
        'role': ROLE_DEPARTMENT_HEAD,
        'job_title': 'TP Sản xuất',
        'is_active': True,
        'sort_order': 1,
    },
)
if not created:
    slot.role = ROLE_DEPARTMENT_HEAD
    slot.is_active = True
    slot.save()
print('slot id', slot.pk, 'created', created)
print('auto_managed:', len(auto_managed_user_ids(u)))
print('report team:', get_report_team_users(u).count())
