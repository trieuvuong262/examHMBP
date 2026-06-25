#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import json
import re
from audit.services.nas_monitor import _dsm_request

data = _dsm_request('SYNO.Core.SyslogClient.Status', 'latestlog_get', version=1, params={'limit': '200'}, timeout=15)
logs = data.get('logs') or []
print('total logs', len(logs))
progs = {}
for log in logs:
    p = log.get('prog') or log.get('orgiProg') or '?'
    progs[p] = progs.get(p, 0) + 1
print('by prog', sorted(progs.items(), key=lambda x: -x[1])[:20])

keywords = re.compile(
    r'file|folder|share|smb|ftp|copy|delete|rename|move|upload|download|write|read|chmod|FileStation|Shared Folder',
    re.I,
)
fileish = [log for log in logs if keywords.search(log.get('msg') or '') or keywords.search(log.get('prog') or '')]
print('fileish', len(fileish))
for log in fileish[:15]:
    print(json.dumps(log, ensure_ascii=False)[:300])
PYEOF
