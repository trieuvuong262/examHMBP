#!/usr/bin/env python3
"""Mô phỏng tp.tb xem detail → khóa nv.tb."""
import os
import sys
import django

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model

from hrm.permissions import can_submit_daily_report
from reports.models import DailyWorkReport
from reports.production_hourly import can_edit_production_report, lock_production_report_on_supervisor_view

User = get_user_model()
tp = User.objects.get(username='tp.tb')
nv = User.objects.get(username='nv.tb')
r = DailyWorkReport.objects.filter(employee=nv).order_by('-report_date').first()
if not r:
    print('no report')
    sys.exit(1)

print('before hod_reviewed:', r.hod_reviewed)
locked = lock_production_report_on_supervisor_view(r, tp)
print('lock called:', locked)
r.refresh_from_db()
print('after hod_reviewed:', r.hod_reviewed)
print('can_edit nv:', can_edit_production_report(nv, r, can_submit=can_submit_daily_report(nv)))
