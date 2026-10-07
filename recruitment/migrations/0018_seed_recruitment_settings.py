"""Dữ liệu ban đầu cho menu Tuyển dụng → Thiết lập.

- Nguồn hồ sơ / Loại hồ sơ: tạo từ danh sách cố định cũ (giữ nguyên mã đã lưu trong hồ sơ).
- Địa điểm họp: lấy từ các lịch phỏng vấn đã nhập.
- Quyền menu ``settings``: sao chép từ menu «Vị trí tuyển dụng» (``jobs``) của từng nhóm quyền.
"""

from django.db import migrations

SOURCES = [
    ('hr', 'HR nhập hồ sơ', False),
    ('walk_in', 'Ứng viên tự đến', False),
    ('online', 'Kênh online', False),
    ('referral', 'Quản lý đề xuất', True),
]
KINDS = [
    ('cv', 'CV / Hồ sơ xin việc', True, True),
    ('other', 'Giấy tờ khác', False, False),
]
ACTIONS = ('view', 'create', 'update', 'delete', 'export', 'print')


def seed(apps, schema_editor):
    CandidateSource = apps.get_model('recruitment', 'CandidateSource')
    CandidateFileKind = apps.get_model('recruitment', 'CandidateFileKind')
    InterviewLocation = apps.get_model('recruitment', 'InterviewLocation')
    Interview = apps.get_model('recruitment', 'Interview')

    for i, (code, name, system) in enumerate(SOURCES):
        CandidateSource.objects.get_or_create(
            code=code, defaults={'name': name, 'is_system': system, 'sort_order': (i + 1) * 10},
        )
    for i, (code, name, is_cv, system) in enumerate(KINDS):
        CandidateFileKind.objects.get_or_create(
            code=code, defaults={'name': name, 'is_cv': is_cv, 'is_system': system, 'sort_order': (i + 1) * 10},
        )
    names = sorted({
        ' '.join(n.split()) for n in Interview.objects.exclude(location='').values_list('location', flat=True)
    } - {''})
    for i, name in enumerate(names):
        InterviewLocation.objects.get_or_create(name=name[:120], defaults={'sort_order': (i + 1) * 10})


def grant(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        entry = perms.get('recruitment')
        if not isinstance(entry, dict) or not isinstance(entry.get('menus'), dict):
            continue
        menus = dict(entry['menus'])
        jobs = menus.get('jobs')
        if 'settings' in menus or not isinstance(jobs, dict) or not any(jobs.get(a) for a in ACTIONS):
            continue
        menus['settings'] = {a: bool(jobs.get(a)) and a not in ('export', 'print') for a in ACTIONS}
        entry = {**entry, 'menus': menus}
        perms['recruitment'] = entry
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def forward(apps, schema_editor):
    seed(apps, schema_editor)
    grant(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0017_recruitment_settings'),
        ('hrm', '0118_recruitment_under_hrm'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
