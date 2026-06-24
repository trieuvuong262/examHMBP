#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose cp /tmp/nas_monitor.py web:/app/audit/services/nas_monitor.py
docker compose exec -T web python manage.py shell <<'PYEOF'
import time
from audit.services.nas_monitor import _read_dsm_volumes, _collect_shares

t0 = time.time()
vols = _read_dsm_volumes()
shares = _collect_shares(volumes=vols)
print('elapsed', round(time.time() - t0, 1), 's')
print('volumes', len(vols), vols[0]['display'] if vols else 'none')
print('shares', len(shares))
for s in shares:
    print(s['name'], '|', s.get('display'), '| pct=', s.get('used_percent'))
PYEOF
