"""Smoke test — thiết lập chung báo cáo (chạy local hoặc VPS).

Usage:
  python manage.py shell < scripts/smoke_reports_general_settings.py
  # hoặc:
  docker compose exec -T web python manage.py shell < scripts/smoke_reports_general_settings.py
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from reports.forms_settings import ReportsGeneralSettingsForm
from reports.models import DailyWorkReport, ReportsGeneralSettings
from reports.production_report_reminders import (
    KIND_MORNING,
    KIND_NIGHT,
    auto_submit_report_date,
    is_auto_submit_window,
)
from reports.production_hourly import viewer_may_edit_stage_time
from reports.report_lock import (
    production_approve_deadline,
    production_auto_reject_deadline,
    production_employee_edit_deadline,
    production_manager_edit_deadline,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.report_settings import (
    allow_edit_wrong_stage_time,
    managers_may_edit_stage_time,
    report_approve_deadline_hours,
    report_auto_reject_deadline_hours,
    report_auto_submit_time,
    report_employee_edit_deadline_hours,
    report_max_quantity_efficiency_pct,
    report_max_time_efficiency_pct,
    report_night_auto_submit_enabled,
    report_night_auto_submit_time,
    report_night_default_declared_work_hours,
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


def _form_data(**overrides):
    base = {
        'workers_may_edit_stage_time': True,
        'managers_may_edit_stage_time': True,
        'allow_edit_wrong_stage_time': True,
        'max_time_efficiency_pct': 200,
        'max_quantity_efficiency_pct': 200,
        'auto_submit_time': '23:30',
        'default_declared_work_hours': '9.50',
        'night_auto_submit_enabled': True,
        'night_auto_submit_time': '05:00',
        'night_default_declared_work_hours': '9.50',
        'auto_approve_proxy_reports': True,
        'auto_approve_manager_edited_reports': True,
        'work_hours_min': '7.50',
        'work_hours_max': '16',
        'approve_deadline_hours': 24,
        'auto_reject_deadline_hours': 24,
        'employee_edit_deadline_hours': 24,
        'unapprove_deadline_days': 7,
    }
    base.update(overrides)
    return base


print('=== ReportsGeneralSettings smoke ===')

cfg = ReportsGeneralSettings.load()
if cfg.pk != 1:
    fail('singleton pk', f'got {cfg.pk}')
else:
    ok('singleton load pk=1')

# Snapshot để restore
snap_fields = (
    'workers_may_edit_stage_time',
    'managers_may_edit_stage_time',
    'allow_edit_wrong_stage_time',
    'max_time_efficiency_pct',
    'max_quantity_efficiency_pct',
    'auto_submit_time',
    'default_declared_work_hours',
    'night_auto_submit_enabled',
    'night_auto_submit_time',
    'night_default_declared_work_hours',
    'auto_approve_proxy_reports',
    'auto_approve_manager_edited_reports',
    'work_hours_min',
    'work_hours_max',
    'approve_deadline_hours',
    'auto_reject_deadline_hours',
    'employee_edit_deadline_hours',
    'unapprove_deadline_days',
)
snap = {k: getattr(cfg, k) for k in snap_fields}

try:
    cfg.workers_may_edit_stage_time = False
    cfg.managers_may_edit_stage_time = False
    cfg.allow_edit_wrong_stage_time = True
    cfg.max_time_efficiency_pct = 150
    cfg.max_quantity_efficiency_pct = 180
    cfg.auto_submit_time = time(22, 15)
    cfg.default_declared_work_hours = Decimal('9.50')
    cfg.night_auto_submit_enabled = True
    cfg.night_auto_submit_time = time(5, 0)
    cfg.night_default_declared_work_hours = Decimal('8.00')
    cfg.approve_deadline_hours = 12
    cfg.auto_reject_deadline_hours = 36
    cfg.employee_edit_deadline_hours = 18
    cfg.unapprove_deadline_days = 5
    cfg.save()

    checks = [
        (workers_may_edit_stage_time() is False, 'workers_may_edit_stage_time=False'),
        (managers_may_edit_stage_time() is False, 'managers_may_edit_stage_time=False'),
        (allow_edit_wrong_stage_time() is True, 'allow_edit_wrong_stage_time=True'),
        (report_max_time_efficiency_pct() == 150, 'max_time_efficiency_pct=150'),
        (report_max_quantity_efficiency_pct() == 180, 'max_quantity_efficiency_pct=180'),
        (report_auto_submit_time() == time(22, 15), 'auto_submit_time=22:15'),
        (report_night_auto_submit_enabled() is True, 'night_auto_submit_enabled=True'),
        (report_night_auto_submit_time() == time(5, 0), 'night_auto_submit_time=05:00'),
        (report_night_default_declared_work_hours() == Decimal('8.00'), 'night_default_hours=8.00'),
        (report_approve_deadline_hours() == 12, 'approve_deadline_hours=12'),
        (report_auto_reject_deadline_hours() == 36, 'auto_reject_deadline_hours=36'),
        (report_employee_edit_deadline_hours() == 18, 'employee_edit_deadline_hours=18'),
        (report_unapprove_deadline_days() == 5, 'unapprove_deadline_days=5'),
    ]
    for passed, label in checks:
        if passed:
            ok(label)
        else:
            fail(label)

    # Override: tắt quyền sửa giờ thường nhưng bật «báo cáo sai» → vẫn sửa được khi for_wrong_stage
    admin_user = get_user_model().objects.filter(is_superuser=True).first()
    worker = get_user_model().objects.order_by('id').first()
    if admin_user and worker:
        fake_report = DailyWorkReport(employee=worker)
        if viewer_may_edit_stage_time(admin_user, fake_report):
            fail('manager should not edit stage time when managers_may_edit=False')
        else:
            ok('managers_may_edit=False blocks normal stage time edit')
        if not viewer_may_edit_stage_time(admin_user, fake_report, for_wrong_stage=True):
            fail('for_wrong_stage should allow stage time when allow_edit_wrong=True')
        else:
            ok('for_wrong_stage allows stage time despite managers_may_edit=False')
        cfg.allow_edit_wrong_stage_time = False
        cfg.save()
        if viewer_may_edit_stage_time(admin_user, fake_report, for_wrong_stage=True):
            fail('for_wrong_stage should block when allow_edit_wrong=False')
        else:
            ok('for_wrong_stage blocked when allow_edit_wrong=False')
        cfg.allow_edit_wrong_stage_time = True
        cfg.save()
    else:
        ok('skip wrong-stage override (no users)')

    # Form: Y < X bị từ chối
    bad = ReportsGeneralSettingsForm(
        data=_form_data(approve_deadline_hours=24, auto_reject_deadline_hours=12),
        instance=cfg,
    )
    if bad.is_valid():
        fail('form should reject Y < X')
    else:
        ok('form rejects auto_reject < approve')

    good = ReportsGeneralSettingsForm(
        data=_form_data(approve_deadline_hours=12, auto_reject_deadline_hours=24),
        instance=cfg,
    )
    if not good.is_valid():
        fail('form should accept Y >= X', str(good.errors))
    else:
        ok('form accepts Y >= X')

    bad_night_hours = ReportsGeneralSettingsForm(
        data=_form_data(night_default_declared_work_hours='20'),
        instance=cfg,
    )
    if bad_night_hours.is_valid():
        fail('form should reject night hours out of range')
    else:
        ok('form rejects night default hours out of range')

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
        approve_dl = production_approve_deadline(report)
        reject_dl = production_auto_reject_deadline(report)
        edit_dl = production_employee_edit_deadline(report)
        if not approve_dl or abs((approve_dl - now - timedelta(hours=12)).total_seconds()) > 2:
            fail('approve deadline not ~12h', str(approve_dl))
        else:
            ok('approve deadline = submitted + 12h')
        if not reject_dl or abs((reject_dl - now - timedelta(hours=36)).total_seconds()) > 2:
            fail('reject deadline not ~36h', str(reject_dl))
        else:
            ok('reject deadline = submitted + 36h')
        if not edit_dl or abs((edit_dl - now - timedelta(hours=18)).total_seconds()) > 2:
            fail('employee edit deadline not ~18h', str(edit_dl))
        else:
            ok('employee edit deadline = submitted + 18h')

        report.hod_reviewed = True
        report.hod_reviewed_at = now
        mgr_dl = production_manager_edit_deadline(report)
        if not mgr_dl or abs((mgr_dl - now - timedelta(days=5)).total_seconds()) > 2:
            fail('unapprove deadline not ~5d', str(mgr_dl))
        else:
            ok('unapprove deadline = reviewed + 5d')

    # Auto-submit windows
    today = timezone.localdate()
    morn_in = timezone.make_aware(datetime.combine(today, time(22, 17)))
    morn_out = timezone.make_aware(datetime.combine(today, time(22, 14)))
    night_in = timezone.make_aware(datetime.combine(today, time(5, 2)))
    night_out = timezone.make_aware(datetime.combine(today, time(4, 59)))

    if not is_auto_submit_window(now=morn_in, kind=KIND_MORNING):
        fail('morning window inside grace')
    else:
        ok('morning auto-submit window inside grace')
    if is_auto_submit_window(now=morn_out, kind=KIND_MORNING):
        fail('morning window before target')
    else:
        ok('morning auto-submit window closed before target')
    if not is_auto_submit_window(now=night_in, kind=KIND_NIGHT):
        fail('night window inside grace')
    else:
        ok('night auto-submit window inside grace')
    if is_auto_submit_window(now=night_out, kind=KIND_NIGHT):
        fail('night window before target')
    else:
        ok('night auto-submit window closed before target')
    if is_auto_submit_window(now=night_in, kind=KIND_MORNING):
        fail('night time should not open morning window')
    else:
        ok('night time does not open morning window')

    if auto_submit_report_date(kind=KIND_MORNING) != today:
        fail('morning report_date should be today')
    else:
        ok('morning report_date = today')
    if auto_submit_report_date(kind=KIND_NIGHT) != today - timedelta(days=1):
        fail('night report_date should be yesterday')
    else:
        ok('night report_date = yesterday')

    # Page content has night fields
    url = reverse('reports:general_settings')
    if url != '/reports/sx/thiet-lap/':
        fail('settings URL', url)
    else:
        ok(f'settings URL {url}')

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
            body = r.content.decode('utf-8', errors='ignore')
            ok(f'GET settings as {admin.username} -> 200')
            for needle in (
                'id_managers_may_edit_stage_time',
                'id_allow_edit_wrong_stage_time',
                'id_max_time_efficiency_pct',
                'id_max_quantity_efficiency_pct',
                'id_auto_submit_time',
                'id_night_auto_submit_enabled',
                'id_night_auto_submit_time',
                'id_night_default_declared_work_hours',
                'id_approve_deadline_hours',
                'id_auto_reject_deadline_hours',
            ):
                if needle in body:
                    ok(f'page contains {needle}')
                else:
                    fail(f'page missing {needle}')
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

    # Cron dry-run: cả morning + night khi force
    from reports.production_report_reminders import auto_submit_unsubmitted_production_reports

    stats = auto_submit_unsubmitted_production_reports(dry_run=True, force=True)
    if stats.get('failed', 0) != 0:
        fail('force dry-run failed', str(stats))
    else:
        ok(
            f"force dry-run submitted={stats.get('submitted', 0)} "
            f"skipped={stats.get('skipped', 0)} failed=0"
        )

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
