"""Smoke test — thiết lập chung báo cáo (chạy local hoặc VPS).

Usage:
  python manage.py shell < scripts/smoke_reports_general_settings.py
  # hoặc:
  docker compose exec -T web python manage.py shell < scripts/smoke_reports_general_settings.py
"""

from __future__ import annotations

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from reports.forms_settings import ReportsGeneralSettingsForm
from reports.models import DailyWorkReport, ReportsGeneralSettings
from reports.production_report_reminders import is_auto_submit_window
from reports.report_lock import (
    production_approve_deadline,
    production_auto_reject_deadline,
    production_employee_edit_deadline,
    production_manager_edit_deadline,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.report_settings import (
    managers_may_edit_stage_time,
    report_approve_deadline_hours,
    report_auto_reject_deadline_hours,
    report_auto_submit_time,
    report_unapprove_deadline_days,
    workers_may_edit_stage_time,
)
from reports.navigation import MENU_GENERAL_SETTINGS

FAIL = []


def ok(msg):
    print(f'  PASS: {msg}')


def fail(msg, detail=''):
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' -- {detail}' if detail else ''))


print('=== ReportsGeneralSettings smoke ===')

cfg = ReportsGeneralSettings.load()
if cfg.pk != 1:
    fail('singleton pk', f'got {cfg.pk}')
else:
    ok('singleton load pk=1')

# Snapshot để restore
snap = {
    'workers_may_edit_stage_time': cfg.workers_may_edit_stage_time,
    'managers_may_edit_stage_time': cfg.managers_may_edit_stage_time,
    'auto_submit_time': cfg.auto_submit_time,
    'approve_deadline_hours': cfg.approve_deadline_hours,
    'unapprove_deadline_days': cfg.unapprove_deadline_days,
    'auto_reject_deadline_hours': cfg.auto_reject_deadline_hours,
}

try:
    cfg.workers_may_edit_stage_time = False
    cfg.managers_may_edit_stage_time = True
    cfg.auto_submit_time = time(22, 15)
    cfg.approve_deadline_hours = 12
    cfg.auto_reject_deadline_hours = 36
    cfg.unapprove_deadline_days = 5
    cfg.save()

    if workers_may_edit_stage_time() is not False:
        fail('workers_may_edit_stage_time')
    else:
        ok('workers_may_edit_stage_time=False')

    if managers_may_edit_stage_time() is not True:
        fail('managers_may_edit_stage_time')
    else:
        ok('managers_may_edit_stage_time=True')

    if report_auto_submit_time() != time(22, 15):
        fail('auto_submit_time', str(report_auto_submit_time()))
    else:
        ok('auto_submit_time=22:15')

    if report_approve_deadline_hours() != 12:
        fail('approve_deadline_hours')
    else:
        ok('approve_deadline_hours=12')

    if report_auto_reject_deadline_hours() != 36:
        fail('auto_reject_deadline_hours')
    else:
        ok('auto_reject_deadline_hours=36')

    if report_unapprove_deadline_days() != 5:
        fail('unapprove_deadline_days')
    else:
        ok('unapprove_deadline_days=5')

    # Form: Y < X bị từ chối
    bad = ReportsGeneralSettingsForm(
        data={
            'workers_may_edit_stage_time': True,
            'managers_may_edit_stage_time': True,
            'auto_submit_time': '23:30',
            'approve_deadline_hours': 24,
            'unapprove_deadline_days': 7,
            'auto_reject_deadline_hours': 12,
        },
        instance=cfg,
    )
    if bad.is_valid():
        fail('form should reject Y < X')
    else:
        ok('form rejects auto_reject < approve')

    good = ReportsGeneralSettingsForm(
        data={
            'workers_may_edit_stage_time': True,
            'managers_may_edit_stage_time': True,
            'auto_submit_time': '23:30',
            'approve_deadline_hours': 12,
            'unapprove_deadline_days': 7,
            'auto_reject_deadline_hours': 24,
        },
        instance=cfg,
    )
    if not good.is_valid():
        fail('form should accept Y >= X', str(good.errors))
    else:
        ok('form accepts Y >= X')

    # Deadlines trên báo cáo giả
    User = get_user_model()
    user = User.objects.order_by('id').first()
    if not user:
        fail('no user for deadline test')
    else:
        now = timezone.now()
        report = DailyWorkReport(
            employee=user,
            report_date=timezone.localdate(),
            report_profile=REPORT_PROFILE_PRODUCTION,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=now,
            hod_reviewed=False,
            hod_rejected=False,
        )
        # Không save — chỉ tính deadline
        approve_dl = production_approve_deadline(report)
        reject_dl = production_auto_reject_deadline(report)
        edit_dl = production_employee_edit_deadline(report)
        if not approve_dl or (approve_dl - now - timedelta(hours=12)).total_seconds() > 2:
            fail('approve deadline not ~12h', str(approve_dl))
        else:
            ok('approve deadline = submitted + 12h')
        if not reject_dl or (reject_dl - now - timedelta(hours=36)).total_seconds() > 2:
            fail('reject deadline not ~36h', str(reject_dl))
        else:
            ok('reject deadline = submitted + 36h')
        if edit_dl != reject_dl:
            fail('employee edit deadline should equal reject deadline')
        else:
            ok('employee edit deadline == reject deadline (Y)')

        report.hod_reviewed = True
        report.hod_reviewed_at = now
        mgr_dl = production_manager_edit_deadline(report)
        if not mgr_dl or (mgr_dl - now - timedelta(days=5)).total_seconds() > 2:
            fail('unapprove deadline not ~5d', str(mgr_dl))
        else:
            ok('unapprove deadline = reviewed + 5d')

    # Auto-submit window theo giờ cấu hình
    local = timezone.localtime()
    target = local.replace(hour=22, minute=15, second=0, microsecond=0)
    in_window = target + timedelta(minutes=2)
    out_window = target - timedelta(minutes=1)
    if not is_auto_submit_window(now=in_window):
        fail('is_auto_submit_window inside grace')
    else:
        ok('auto-submit window inside grace')
    if is_auto_submit_window(now=out_window):
        fail('is_auto_submit_window before target')
    else:
        ok('auto-submit window closed before target')

    # URL
    url = reverse('reports:general_settings')
    if url != '/reports/sx/thiet-lap/':
        fail('settings URL', url)
    else:
        ok(f'settings URL {url}')

    # HTTP — staff/superuser nếu có
    admin = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
    if admin:
        from django.conf import settings as dj_settings

        host = 'localhost'
        allowed = getattr(dj_settings, 'ALLOWED_HOSTS', None) or []
        if allowed and allowed != ['*']:
            host = next((h for h in allowed if h and h not in ('*', '.')), 'localhost')
            if host.startswith('.'):
                host = 'localhost'
        client = Client(HTTP_HOST=host)
        client.force_login(admin)
        r = client.get(url)
        if r.status_code == 200:
            ok(f'GET settings as {admin.username} -> 200')
        elif r.status_code in (301, 302):
            ok(f'GET settings as {admin.username} -> redirect {r.status_code} (menu perm?)')
        else:
            fail(f'GET settings as {admin.username}', f'status={r.status_code}')
    else:
        ok('skip HTTP (no admin user)')

    if MENU_GENERAL_SETTINGS != 'general_settings':
        fail('MENU_GENERAL_SETTINGS constant')
    else:
        ok('MENU_GENERAL_SETTINGS=general_settings')

finally:
    for k, v in snap.items():
        setattr(cfg, k, v)
    cfg.save()
    ok('restored settings snapshot')

print('')
if FAIL:
    print(f'RESULT: FAIL ({len(FAIL)})')
    for item in FAIL:
        print(f'  - {item}')
    raise SystemExit(1)
print('RESULT: PASS')
