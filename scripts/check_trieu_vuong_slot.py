"""Debug slot kiêm nhiệm Lê Nguyễn Triều Vương."""
from django.contrib.auth.models import User

from hrm.models import Department, ProfileConcurrentPosition
from hrm.permissions import get_report_team_users, ROLE_DEPARTMENT_HEAD
from hrm.user_search import subordinate_candidate_queryset

users = User.objects.filter(profile__full_name__icontains='triều vương') | User.objects.filter(
    profile__full_name__icontains='trieu vuong',
)
users = users.select_related('profile').distinct()
if not users.exists():
    users = User.objects.filter(username__icontains='vuong').select_related('profile')[:5]

for u in users:
    p = u.profile
    print('===', u.username, '|', p.full_name, '===')
    print('  role chính:', p.role, p.get_role_display())
    print('  dept:', p.department, '| div:', p.division)
    print('  subordinates chính:', list(p.subordinates.values_list('username', flat=True)))
    slots = ProfileConcurrentPosition.objects.filter(profile=p).order_by('sort_order', 'id')
    for i, cp in enumerate(slots, 1):
        print(f'  Slot {i}: id={cp.pk} active={cp.is_active}')
        print(f'    dept={cp.department_id} {cp.department} | div={cp.division_id} {cp.division}')
        print(f'    role={cp.role} | job={cp.job_position}')
        subs = list(cp.subordinates.values_list('username', flat=True))
        print(f'    subs M2M: {subs}')
        qs = subordinate_candidate_queryset(
            exclude_user_id=u.pk,
            manager_role=cp.role,
            department_id=cp.department_id,
            division_id=cp.division_id,
            extra_user_ids=list(cp.subordinates.values_list('pk', flat=True)),
        )
        print(f'    candidate count: {qs.count()}')
        if qs.count() <= 15:
            for c in qs:
                print(f'      - {c.username} ({c.profile.full_name})')
    team = get_report_team_users(u)
    print('  report team size:', team.count())
