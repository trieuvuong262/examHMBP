#!/usr/bin/env python3
"""Chẩn đoán NAS monitor trên VPS — chạy: docker compose exec web python scripts/diagnose_nas_metrics.py"""
import json
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from audit.services.nas_monitor import (  # noqa: E402
    NasMonitorError,
    _dsm_request,
    _rclone_about,
    collect_nas_metrics,
    dsm_configured,
)
from nas_storage.nas_paths import default_nas_rclone_remote, rclone_listing_available  # noqa: E402


def main() -> int:
    print('=== NAS Monitor Diagnostic ===')
    print('dsm_configured:', dsm_configured())
    print('rclone_available:', rclone_listing_available())
    print('NAS_DSM_URL:', os.getenv('NAS_DSM_URL', '(settings default)'))

    try:
        metrics = collect_nas_metrics()
    except Exception as exc:
        print('collect_nas_metrics FAILED:', exc)
        return 1

    print('error:', metrics.get('error'))
    print('cpu:', json.dumps(metrics.get('cpu'), ensure_ascii=False))
    print('ram:', json.dumps(metrics.get('ram'), ensure_ascii=False))
    print('disk:', json.dumps(metrics.get('disk'), ensure_ascii=False))
    print('--- shares (%d) ---' % len(metrics.get('shares') or []))
    for row in metrics.get('shares') or []:
        print(
            '  %-20s display=%-28s used=%s total=%s pct=%s'
            % (
                row.get('name'),
                row.get('display'),
                row.get('used_bytes'),
                row.get('total_bytes'),
                row.get('used_percent'),
            )
        )
    print('--- volumes (%d) ---' % len(metrics.get('volumes') or []))
    for row in metrics.get('volumes') or []:
        print(
            '  %-20s display=%-28s pct=%s status=%s'
            % (row.get('name'), row.get('display'), row.get('used_percent'), row.get('status'))
        )

    if dsm_configured():
        print('--- DSM list_share (first 3) ---')
        try:
            data = _dsm_request(
                'SYNO.FileStation.List',
                'list_share',
                version=2,
                params={'additional': '["size","real_path","volume_status"]', 'limit': '0'},
                timeout=20,
            )
            for sh in (data.get('shares') or [])[:3]:
                print(' ', sh.get('name'), json.dumps(sh.get('additional'), ensure_ascii=False))
        except NasMonitorError as exc:
            print(' list_share error:', exc)

    remote = default_nas_rclone_remote()
    print('--- rclone remote base:', remote, '---')
    if rclone_listing_available():
        import subprocess
        proc = subprocess.run(
            ['rclone', 'lsd', remote, '--json'],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                names = [e.get('Name') or e.get('name') for e in json.loads(proc.stdout)[:5]]
            except json.JSONDecodeError:
                names = []
            for name in names:
                if not name:
                    continue
                path = f'{remote}{name}' if remote.endswith(':') else f'{remote.rstrip("/")}/{name}'
                about = _rclone_about(path, timeout=12)
                print(' ', name, about)
    return 0


if __name__ == '__main__':
    sys.exit(main())
