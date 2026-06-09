"""Kiểm tra báo cáo NV phòng MKT — giám đốc vs kiêm nhiệm trưởng phòng."""
from django.contrib.auth.models import User

from hrm.concurrent_positions import auto_managed_user_ids
from hrm.models import Department, ProfileConcurrentPosition
from hrm.permissions import get_report_team_users
from reports.models import DailyWorkReport

dept = Department.objects.filter(name__icontains='MARKETING').first()
print('=== PHÒNG MKT ===')
if not dept:
    print('KHÔNG TÌM THẤY phòng KINH DOANH - MARKETING')
    raise SystemExit(1)
print(f'Dept: {dept.name} (id={dept.pk})')

directors = User.objects.filter(
    profile__role='DIRECTOR',
    profile__is_employed=True,
    is_active=True,
).select_related('profile')
print('\n=== GIÁM ĐỐC ===')
for d in directors:
    team = get_report_team_users(d)
    mkt_in_team = team.filter(profile__department=dept).count()
    print(
        f'  {d.username} | {d.profile.full_name} | '
        f'team={team.count()} | mkt_in_team={mkt_in_team}',
    )

mkt_emps = (
    User.objects.filter(
        profile__department=dept,
        profile__is_employed=True,
        is_active=True,
    )
    .exclude(profile__role='DIRECTOR')
    .select_related('profile')
    .order_by('profile__full_name')
)
print(f'\n=== NV PHÒNG MKT ({mkt_emps.count()} người) ===')
for u in mkt_emps:
    last = DailyWorkReport.objects.filter(employee=u).order_by('-report_date').first()
    if last:
        last_info = f'{last.report_date} {last.status}'
    else:
        last_info = 'chưa có'
    print(
        f'  {u.username} | {u.profile.full_name} | '
        f'role={u.profile.get_role_display()} | báo cáo gần nhất: {last_info}',
    )

print('\n=== KIÊM NHIỆM TRƯỞNG PHÒNG MKT ===')
conc = ProfileConcurrentPosition.objects.filter(
    is_active=True,
    department=dept,
    role='DEPARTMENT_HEAD',
).select_related('profile__user', 'profile__department', 'division')
if not conc.exists():
    print('  (không có slot kiêm nhiệm DEPARTMENT_HEAD tại phòng MKT)')
for cp in conc:
    u = cp.profile.user
    manual = list(
        cp.subordinates.filter(is_active=True, profile__is_employed=True).values_list(
            'username', flat=True,
        ),
    )
    team = get_report_team_users(u)
    mkt_team = team.filter(profile__department=dept)
    auto = auto_managed_user_ids(u)
    mkt_auto = User.objects.filter(pk__in=auto, profile__department=dept).count()
    print(f'  User: {u.username} | {cp.profile.full_name}')
    print(f'    Vai trò chính: {cp.profile.get_role_display()} | PB chính: {cp.profile.department}')
    print(f'    Slot: {cp.job_position or cp.job_title} | BP: {cp.division}')
    print(f'    Cấp dưới thủ công (slot): {manual}')
    print(
        f'    Team báo cáo: {team.count()} | NV MKT trong team: {mkt_team.count()} | '
        f'auto-scope MKT: {mkt_auto}',
    )
    for m in mkt_team:
        print(f'      ✓ {m.username} ({m.profile.full_name})')

print('\n=== TRƯỞNG PHÒNG MKT (vai trò chính) ===')
primary_heads = User.objects.filter(
    profile__department=dept,
    profile__role='DEPARTMENT_HEAD',
    profile__is_employed=True,
    is_active=True,
)
if not primary_heads.exists():
    print('  (không có Trưởng phòng primary tại MKT)')
for h in primary_heads:
    team = get_report_team_users(h)
    print(
        f'  {h.username} | {h.profile.full_name} | '
        f'team={team.count()} | mkt={team.filter(profile__department=dept).count()}',
    )

print('\n=== KIỂM TRA: NV MKT thuộc team ai? ===')
for u in mkt_emps:
    viewers = []
    for d in directors:
        if get_report_team_users(d).filter(pk=u.pk).exists():
            viewers.append(f'GD:{d.username}')
    for cp in conc:
        mgr = cp.profile.user
        if get_report_team_users(mgr).filter(pk=u.pk).exists():
            viewers.append(f'Kiêm-TP:{mgr.username}')
    for h in primary_heads:
        if get_report_team_users(h).filter(pk=u.pk).exists():
            viewers.append(f'TP:{h.username}')
    print(f'  {u.username} → {", ".join(viewers) if viewers else "KHÔNG AI XEM ĐƯỢC"}')
