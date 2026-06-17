#!/usr/bin/env python3
"""Kiểm tra trạng thái khóa báo cáo tp.tb / nv.tb trên VPS hoặc local."""
import os
import sys
import django

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from hrm.permissions import (
    can_review_user_report,
    can_view_user_report,
    can_submit_daily_report,
    get_report_team_users,
)
from reports.models import DailyWorkReport
from reports.production_hourly import (
    can_edit_production_report,
    is_production_report_locked,
    lock_production_report_on_supervisor_view,
)

User = get_user_model()
tp = User.objects.get(username='tp.tb')
nv = User.objects.get(username='nv.tb')
r = DailyWorkReport.objects.filter(employee=nv).order_by('-report_date').first()
print('tp team:', list(get_report_team_users(tp).values_list('username', flat=True)))
if not r:
    print('no report for nv.tb')
    sys.exit(0)
print('report pk:', r.pk)
print('date:', r.report_date)
print('status:', r.status)
print('hod_reviewed:', r.hod_reviewed)
print('shift_started_at:', r.shift_started_at)
print('is_production:', r.is_production_report)
print('can_review tp:', can_review_user_report(tp, r))
print('can_view tp:', can_view_user_report(tp, r))
print('can_edit nv:', can_edit_production_report(nv, r, can_submit=can_submit_daily_report(nv)))
print('is_locked:', is_production_report_locked(r))
print('lock_would_run:', lock_production_report_on_supervisor_view.__name__)
