#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import json
from audit.services.nas_monitor import _dsm_request, _read_dsm_share_quotas, collect_nas_processes, _collect_shares, _read_dsm_volumes, _read_dsm_utilization

# share quota sample
qm = _read_dsm_share_quotas()
for name in ['backup', '05_MARKETING', '10_HE_THONG_CNTT']:
    print('quota', name, json.dumps(qm.get(name), default=str))

vols = _read_dsm_volumes()
shares = _collect_shares(volumes=vols)
for s in shares:
    if s['name'] in ('backup', '05_MARKETING', '10_HE_THONG_CNTT'):
        print('share', s['name'], s.get('display'), 'used', s.get('used_bytes'), 'total', s.get('total_bytes'), 'free', s.get('free_bytes'))

# processes raw
data = _dsm_request('SYNO.Core.System.Process', 'list', version=1, timeout=15)
procs = (data.get('process') or data.get('processes') or [])[:5]
for p in procs[:3]:
    print('proc', {k: p.get(k) for k in ('name','pid','memory','mem','memory_percent','cpu')})

util = _read_dsm_utilization()
print('ram total', util.get('ram', {}).get('total_bytes'))
rows = collect_nas_processes(limit=5)
for r in rows[:5]:
    print('parsed', r)
PYEOF
