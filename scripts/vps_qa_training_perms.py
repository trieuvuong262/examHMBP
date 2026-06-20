"""QA phân quyền & workflow Đào tạo trên VPS — chạy: python manage.py shell < scripts/vps_qa_training_perms.py"""
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from hrm.context_processors import portal_permissions, _can_manage_module
from hrm.module_permissions import (
    MODULE_ASSESSMENT,
    MODULE_TRAINING,
    user_can_access_module,
    user_can_create_module,
    user_can_delete_module,
    user_can_edit_module,
    user_can_update_module,
)
from hrm.models import Profile
from training.models import Course, Enrollment

HOST = 'portal.justplay.vn'


def perm_row(user):
    ctx = portal_permissions(type('R', (), {'user': user})())
    return {
        'can_training': user_can_access_module(user, MODULE_TRAINING),
        'can_assessment': user_can_access_module(user, MODULE_ASSESSMENT),
        'view': ctx.get('jp_can_training'),
        'manage_training': ctx.get('jp_can_manage_training'),
        'manage_assessment': ctx.get('jp_can_manage_assessment'),
        'create': user_can_create_module(user, MODULE_TRAINING),
        'update': user_can_update_module(user, MODULE_TRAINING),
        'delete': user_can_delete_module(user, MODULE_TRAINING),
        'edit': user_can_edit_module(user, MODULE_TRAINING),
    }


def hit(client, url_name, *args, method='get'):
    url = reverse(url_name, args=args) if args else reverse(url_name)
    fn = getattr(client, method)
    return fn(url, HTTP_HOST=HOST)


def expect_status(client, url_name, code, *args, label=''):
    resp = hit(client, url_name, *args)
    ok = resp.status_code == code
    mark = 'OK' if ok else f'FAIL got {resp.status_code} -> {getattr(resp, "url", "")}'
    print(f'    {label or url_name}: {mark}')
    return ok


print('=== TRAINING PERMISSION QA ===\n')

# Sample users: view-only employee, editor, admin, director
candidates = []
for u in User.objects.filter(is_active=True).select_related('profile')[:200]:
    p = perm_row(u)
    if not p['can_training'] and not p['manage_training'] and not p['can_assessment']:
        continue
    candidates.append((u, p))

# classify
view_only = []
both = []
manage_only = []
for u, p in candidates:
    if p['view'] and p['manage_training']:
        both.append((u, p))
    elif p['view'] and not p['manage_training']:
        view_only.append((u, p))
    elif p['manage_training'] and not p['view']:
        manage_only.append((u, p))

print(f'Users with training/assessment access: {len(candidates)}')
print(f'  view only: {len(view_only)}')
print(f'  view + manage: {len(both)}')
print(f'  manage only (no view): {len(manage_only)}')

issues = []


def run_user_tests(user, p, tag):
    global issues
    print(f'\n--- {tag}: {user.username} ({getattr(user.profile, "full_name", "")}) ---')
    print(f'    perms: view={p["view"]} manage_tr={p["manage_training"]} create={p["create"]} update={p["update"]} edit={p["edit"]}')

    c = Client()
    c.force_login(user)

    if p['view']:
        if not expect_status(c, 'my_courses', 200, label='my_courses (Bài học)'):
            issues.append(f'{user.username}: view user blocked from my_courses')
        course = Course.objects.filter(assigned_users=user, is_active=True).first()
        if course:
            if not expect_status(c, 'course_start', 200, course.pk, label='course_start'):
                issues.append(f'{user.username}: blocked from learning_space')
    else:
        if expect_status(c, 'my_courses', 302, label='my_courses should block'):
            pass
        else:
            issues.append(f'{user.username}: no view but my_courses returned 200')

    if p['manage_training']:
        if not expect_status(c, 'course_list', 200, label='course_list (Quản lý BH)'):
            issues.append(f'{user.username}: manager blocked from course_list')
        if p['create']:
            if not expect_status(c, 'course_create', 200, label='course_create'):
                issues.append(f'{user.username}: create perm but course_create blocked')
        else:
            expect_status(c, 'course_create', 302, label='course_create should block')
    else:
        if hit(c, 'course_list').status_code == 200:
            issues.append(f'{user.username}: no manage but course_list allowed')
            print('    course_list: FAIL got 200 (should block)')
        else:
            print('    course_list: OK blocked')

    if p['can_assessment']:
        expect_status(c, 'exam_list', 200, label='exam_list (Kiểm tra)')
    if p['manage_assessment']:
        resp = c.get(reverse('admin_dashboard') + '?tab=assessment', HTTP_HOST=HOST)
        ok = resp.status_code == 200
        print(f'    admin_dashboard assessment: {"OK" if ok else f"FAIL {resp.status_code}"}')
        if not ok:
            issues.append(f'{user.username}: manage assessment blocked')


# Test up to 3 per category
for u, p in view_only[:3]:
    run_user_tests(u, p, 'VIEW ONLY')
for u, p in both[:3]:
    run_user_tests(u, p, 'VIEW+MANAGE')
for u, p in manage_only[:2]:
    run_user_tests(u, p, 'MANAGE ONLY')

# Known accounts
for uname in ('admin', 'Ductn'):
    u = User.objects.filter(username=uname).first()
    if u:
        run_user_tests(u, p=perm_row(u), tag=f'ACCOUNT {uname}')

# Workflow: assigned course + enrollment
print('\n=== WORKFLOW: enrollment sync ===')
sample = Enrollment.objects.select_related('user', 'course').order_by('-id').first()
if sample:
    sample.sync_completion_status()
    print(f'  latest enrollment user={sample.user.username} course={sample.course.title!r} '
          f'progress={sample.progress_percent}% completed={sample.is_completed}')
else:
    print('  (no enrollments)')

assigned_count = Course.objects.filter(is_active=True, assigned_users__isnull=False).distinct().count()
print(f'  active courses with assignees: {assigned_count}')

print('\n=== SUMMARY ===')
if issues:
    print(f'ISSUES ({len(issues)}):')
    for i in issues:
        print(f'  - {i}')
else:
    print('All checked paths OK.')
