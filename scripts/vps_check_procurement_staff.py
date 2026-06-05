import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from hrm.models import Department
from hrm.module_permissions import MODULE_DE_XUAT, user_can_access_module
from service_requests.permissions import get_procurement_staff_candidates
from service_requests.workflow import get_procurement_department

User = get_user_model()

print('=== Procurement department ===')
dept = get_procurement_department()
print('  matched:', dept.name if dept else None, f'(id={dept.id})' if dept else '')

print('\n=== Departments matching thu mua / mua hang ===')
for d in Department.objects.filter(name__icontains='mua').order_by('name')[:20]:
    print(f'  - {d.id}: {d.name}')

print('\n=== Users in procurement dept ===')
if dept:
    users = User.objects.filter(
        profile__department=dept,
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile')
    print('  count:', users.count())
    for u in users:
        print(
            f'  - {u.username}: {u.profile.full_name} | '
            f'de_xuat={user_can_access_module(u, MODULE_DE_XUAT)}',
        )

print('\n=== get_procurement_staff_candidates() ===')
candidates = list(get_procurement_staff_candidates())
print('  count:', len(candidates))
for u in candidates:
    print(f'  - {u.username}: {u.profile.full_name}')

print('\n=== All users with de_xuat module (any dept) ===')
all_dx = [
    u for u in User.objects.filter(is_active=True, profile__is_employed=True).select_related('profile')
    if user_can_access_module(u, MODULE_DE_XUAT)
]
for u in all_dx[:30]:
    dept_name = u.profile.department.name if u.profile.department_id else '-'
    print(f'  - {u.username} ({dept_name})')
