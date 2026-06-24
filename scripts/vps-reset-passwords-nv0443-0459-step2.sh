#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
from hrm.models import Profile

codes = [f'NV{n:04d}' for n in range(443, 460) if n != 449]
profiles = list(Profile.objects.filter(employee_code__in=codes))
for p in profiles:
    p.must_change_password = False
Profile.objects.bulk_update(profiles, ['must_change_password'])
print('must_change_password=False for', len(profiles), 'profiles')
PYEOF
