#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import json
from audit.services.nas_monitor import (
    _dsm_request, _read_dsm_share_quotas, _rclone_size, _rclone_about,
    _share_rclone_remote, _collect_shares, _read_dsm_volumes, _parse_dsm_share_quota,
)

names = ['90_MAU_BIEU_FORM_CHUAN', 'backup']
data = _dsm_request('SYNO.Core.Share', 'list', version=1, params={'shareType': 'all', 'additional': '["share_quota","real_path"]'}, timeout=15)
for s in data.get('shares') or []:
    if s.get('name') in names:
        print('RAW', s.get('name'), json.dumps(s, default=str))

qm = _read_dsm_share_quotas()
for n in names:
    print('quota_map', n, qm.get(n))

for n in names:
    remote = _share_rclone_remote(n, '')
    print(n, 'size', _rclone_size(remote, timeout=60))
    print(n, 'about', _rclone_about(remote, timeout=15))

vols = _read_dsm_volumes()
for s in _collect_shares(volumes=vols):
    if s['name'] in names:
        print('COLLECTED', s)
PYEOF
