#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import json
from audit.services.nas_monitor import (
    _dsm_request,
    _read_dsm_widget_file_changes,
    _read_dsm_widget_recent_logs,
    NasMonitorError,
    dsm_configured,
)

print('dsm_configured', dsm_configured())

calls = [
    ('SYNO.Finder.FileSharing', 'get_changelog', 1, {'limit': '20'}),
    ('SYNO.Core.AuditLog', 'list', 1, {'limit': '20', 'offset': '0'}),
    ('SYNO.LogCenter.History', 'list', 1, {'limit': '20', 'logtype': 'file'}),
    ('SYNO.SynologyDrive.Log', 'list', 1, {'limit': '20'}),
    ('SYNO.LogCenter.Log', 'list', 1, {'limit': '20'}),
    ('SYNO.Core.SyslogClient.Status', 'latestlog_get', 1, {'limit': '20'}),
    ('SYNO.Core.FileServ.Audit', 'list', 1, {'limit': '20'}),
    ('SYNO.Core.FileServ.Audit', 'list', 2, {'limit': '20'}),
    ('SYNO.FileStation.Audit', 'list', 1, {'limit': '20'}),
    ('SYNO.Core.Share', 'list', 1, None),
]

for api, method, ver, params in calls:
    try:
        data = _dsm_request(api, method, version=ver, params=params, timeout=15)
        keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        sample = None
        for k in ('items', 'logs', 'changelog', 'history', 'data', 'tasks'):
            if isinstance(data, dict) and isinstance(data.get(k), list) and data[k]:
                sample = data[k][0]
                break
        print('OK', api, method, 'v' + str(ver), 'keys=', keys, 'sample_keys=', list(sample.keys())[:12] if isinstance(sample, dict) else sample)
    except NasMonitorError as e:
        print('ERR', api, method, 'v' + str(ver), str(e)[:120])
    except Exception as e:
        print('EXC', api, method, 'v' + str(ver), type(e).__name__, str(e)[:120])

print('--- file_changes widget ---')
rows = _read_dsm_widget_file_changes(limit=5)
print('count', len(rows))
print(json.dumps(rows[:3], ensure_ascii=False, indent=2))

print('--- recent_logs widget ---')
logs = _read_dsm_widget_recent_logs(limit=3)
print('count', len(logs))
print(json.dumps(logs[:2], ensure_ascii=False, indent=2))
PYEOF
