#!/usr/bin/env python3
"""Test ductn mở file báo cáo tuần qua URL serve."""
import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth.models import User
from django.conf import settings
from django.test import Client

from reports.models import WeeklyWorkReportAttachment
from reports.week_utils import monday_of
from django.utils import timezone


def main():
    viewer = User.objects.get(username__iexact='ductn')
    week = monday_of(timezone.localdate())
    host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
    client = Client(HTTP_HOST=host)
    client.force_login(viewer)

    atts = (
        WeeklyWorkReportAttachment.objects.filter(
            report__week_start=week,
            kind='FILE',
        )
        .select_related('report__employee')
        .order_by('pk')
    )

    ok = 0
    fail = 0
    for att in atts:
        url = f'/reports/weekly/file/{att.pk}/'
        resp = client.get(url)
        if hasattr(resp, 'streaming_content'):
            content = b''.join(resp.streaming_content)
            size = len(content)
        else:
            content = getattr(resp, 'content', b'') or b''
            size = len(content)
        status = resp.status_code
        ct = resp.get('Content-Type', '')
        mark = 'OK' if status == 200 and size > 1000 else 'FAIL'
        if mark == 'OK':
            ok += 1
        else:
            fail += 1
        print(
            f'[{mark}] att={att.pk} user={att.report.employee.username} '
            f'status={status} bytes={size} type={ct} url={url}'
        )

    print(f'SUMMARY ok={ok} fail={fail}')
    return 1 if fail else 0


if __name__ == '__main__':
    raise SystemExit(main())
