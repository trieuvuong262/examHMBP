#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
from django.contrib.auth.models import User
from hrm.models import Profile

codes = [f'NV{n:04d}' for n in range(443, 460)]
password = 'justplay@123'
found = []
missing = []
for code in codes:
    user = User.objects.filter(username=code).first()
    if not user:
        prof = Profile.objects.filter(employee_code=code).select_related('user').first()
        user = prof.user if prof else None
    if not user:
        missing.append(code)
        continue
    user.set_password(password)
    user.save(update_fields=['password'])
    prof = Profile.objects.filter(user=user).first()
    if prof:
        prof.must_change_password = True
        prof.save(update_fields=['must_change_password'])
    found.append(f'{code} -> {user.username}')

print('RESET_OK', len(found))
for line in found:
    print(' ', line)
if missing:
    print('MISSING', len(missing), ','.join(missing))
PYEOF
