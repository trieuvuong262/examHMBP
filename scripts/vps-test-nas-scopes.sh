#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import time
from audit.services.nas_monitor import collect_nas_metrics

for scope in ('performance', 'overview', 'full'):
    t0 = time.time()
    m = collect_nas_metrics(scope=scope)
    elapsed = round(time.time() - t0, 2)
    print(scope, 'elapsed', elapsed, 's', 'shares', len(m.get('shares') or []), 'widgets', bool((m.get('widgets') or {}).get('connected_users') is not None))
PYEOF
