#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import json
from audit.services.nas_monitor import _dsm_request, NasMonitorError

def try_call(label, api, method, version=1, params=None):
    try:
        data = _dsm_request(api, method, version=version, params=params or {}, timeout=15)
        print('===', label, '===')
        if isinstance(data, dict):
            print('keys', list(data.keys()))
            for k, v in data.items():
                if isinstance(v, list):
                    print(k, 'len', len(v))
                    if v:
                        print('first', json.dumps(v[0], ensure_ascii=False)[:500])
                else:
                    print(k, repr(v)[:200])
        else:
            print(data)
    except NasMonitorError as e:
        print('===', label, 'ERR ===', str(e)[:200])

# LogCenter variants
for params in [
    {'limit': '20', 'offset': '0'},
    {'limit': '20', 'offset': '0', 'logtype': 'file'},
    {'limit': '20', 'offset': '0', 'logtype': 'File'},
    {'limit': '20', 'offset': '0', 'keyword': 'file'},
    {'limit': '20', 'offset': '0', 'target': 'file'},
    {'limit': '20', 'offset': '0', 'logtype': 'filestation'},
    {'limit': '20', 'offset': '0', 'logtype': 'FileStation'},
]:
    try_call(f'LogCenter.History {params}', 'SYNO.LogCenter.History', 'list', 1, params)

for ver in (1, 2, 3):
    try_call(f'LogCenter.Log v{ver}', 'SYNO.LogCenter.Log', 'list', ver, {'limit': '20', 'offset': '0'})

# Syslog with filters
try_call('Syslog latest', 'SYNO.Core.SyslogClient.Status', 'latestlog_get', 1, {'limit': '50'})
try_call('Syslog latest v2', 'SYNO.Core.SyslogClient.Status', 'latestlog_get', 2, {'limit': '50'})

# File station / SMB audit
for api, method, ver in [
    ('SYNO.Core.File', 'audit_list', 1),
    ('SYNO.Core.File', 'list_audit', 1),
    ('SYNO.Core.FileServ.SMB', 'get_audit', 1),
    ('SYNO.Core.FileServ.SMB', 'list_audit', 1),
    ('SYNO.LogCenter.Audit', 'list', 1),
    ('SYNO.LogCenter.Audit', 'list', 2),
    ('SYNO.LogCenter.Client', 'list', 1),
    ('SYNO.LogCenter.Client', 'list', 2),
]:
    try_call(f'{api}.{method}', api, method, ver, {'limit': '20', 'offset': '0'})

# Query API info
try_call('API query File', 'SYNO.API.Info', 'query', 1, {'query': 'File'})
try_call('API query Audit', 'SYNO.API.Info', 'query', 1, {'query': 'Audit'})
try_call('API query Log', 'SYNO.API.Info', 'query', 1, {'query': 'Log'})
PYEOF
