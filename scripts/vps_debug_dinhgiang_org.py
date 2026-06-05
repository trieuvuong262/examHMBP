import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from hrm.permissions import ROLE_DIVISION_HEAD, ROLE_TEAM_LEADER, get_profile
from service_requests.models import ServiceRequest
from service_requests.workflow import (
    find_division_head_manager,
    find_team_leader,
    department_has_team_leaders,
    _needs_team_leader_step,
    _needs_division_head_step,
)

User = get_user_model()
u = User.objects.filter(username__iexact='Dinhgiang').select_related('profile__department').first()
p = get_profile(u)
print('=== Dinhgiang profile ===')
print('  full_name:', p.full_name if p else None)
print('  role:', p.role if p else None)
print('  department:', p.department.name if p and p.department_id else None)

print('\n=== Manager chain ===')
tl = find_team_leader(u)
dh = find_division_head_manager(u)
print('  find_team_leader:', tl.username if tl else None, get_profile(tl).full_name if tl else '')
print('  find_division_head:', dh.username if dh else None, get_profile(dh).full_name if dh else '')

if p and p.department_id:
    print('  dept_has_team_leaders:', department_has_team_leaders(p.department))
    tls = User.objects.filter(
        profile__department=p.department,
        profile__role=ROLE_TEAM_LEADER,
        profile__is_employed=True,
        is_active=True,
    )
    print('  team_leaders_in_dept:', [(x.username, get_profile(x).full_name) for x in tls])
    dhs = User.objects.filter(
        profile__department=p.department,
        profile__role=ROLE_DIVISION_HEAD,
        profile__is_employed=True,
        is_active=True,
    )
    print('  division_heads_in_dept:', [(x.username, get_profile(x).full_name) for x in dhs])

print('\n=== Step needs ===')
print('  needs_team_leader_step:', _needs_team_leader_step(u))
print('  needs_division_head_step:', _needs_division_head_step(u))

print('\n=== Subordinates / managers in DB ===')
from hrm.models import Profile
managers = Profile.objects.filter(subordinates=u, is_employed=True).select_related('user')
print('  direct managers (subordinates reverse):', [
    (m.user.username, m.full_name, m.role) for m in managers
])

req = ServiceRequest.objects.filter(requester=u).order_by('-id').first()
if req:
    s1 = req.steps.order_by('step_order').first()
    print('\n=== Request #8 step1 assignee at create ===')
    print('  current assignee:', s1.assignee.username if s1.assignee_id else 'NULL')
    print('  expected TL:', tl.username if tl else 'NULL')
