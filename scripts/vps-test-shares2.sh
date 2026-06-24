#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
from audit.services.nas_monitor import _rclone_about, _rclone_size, _enrich_shares_from_rclone
from nas_storage.nas_paths import default_nas_rclone_remote, rclone_listing_available
import time

print('rclone_listing_available', rclone_listing_available())
remote = default_nas_rclone_remote()
print('remote', remote)
for name in ['backup', '10_HE_THONG_CNTT', 'docker']:
    p = f"{remote}{name}" if remote.endswith(':') else f"{remote.rstrip('/')}/{name}"
    print('---', name, p)
    print('about', _rclone_about(p, timeout=15))
    print('size', _rclone_size(p, timeout=30))

rows = [{'name': 'backup', 'remote': f'{remote}backup', 'total_bytes': None, 'used_bytes': None, 'display': '—'}]
out = _enrich_shares_from_rclone(rows, volumes=[{'total_bytes': 14*1024**4}], deadline=time.monotonic()+60)
print('enriched', out)
PYEOF
