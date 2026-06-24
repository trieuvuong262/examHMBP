#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
from audit.services.vps_monitor import collect_vps_metrics, collect_host_processes, host_monitoring_available

print('host_ok', host_monitoring_available())
procs = collect_host_processes()
print('processes count', len(procs))
print('sample', procs[:3])
m = collect_vps_metrics(scope='full')
print('full processes', len(m.get('processes', [])))
m2 = collect_vps_metrics(scope='performance')
print('perf processes', len(m2.get('processes', [])))
PYEOF
