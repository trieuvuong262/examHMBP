#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import time
from django.test import Client
from django.contrib.auth.models import User

u = User.objects.filter(is_superuser=True).first()
c = Client(HTTP_HOST='portal.justplay.vn')
c.force_login(u)
paths = [
    ('/nhat-ky/nas/', 'nas page'),
    ('/nhat-ky/vps/', 'vps page'),
    ('/nhat-ky/nas/metrics/?scope=overview', 'nas api overview'),
    ('/nhat-ky/nas/metrics/?scope=performance', 'nas api perf'),
    ('/nhat-ky/vps/metrics/?scope=full', 'vps api full'),
    ('/nhat-ky/vps/metrics/?scope=performance', 'vps api perf'),
]
for path, label in paths:
    t0 = time.time()
    r = c.get(path)
    print(label, round(time.time() - t0, 2), 's', r.status_code)
PYEOF
