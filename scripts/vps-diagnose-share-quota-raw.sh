#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import json
from audit.services.nas_monitor import _dsm_request

data = _dsm_request('SYNO.Core.Share', 'list', version=1, params={'shareType': 'all', 'additional': '["share_quota","real_path"]'}, timeout=15)
for s in data.get('shares') or []:
    if s.get('name') in ('backup', '05_MARKETING'):
        print(json.dumps(s, indent=2, default=str)[:800])
PYEOF
