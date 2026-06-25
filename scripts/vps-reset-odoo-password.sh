#!/usr/bin/env bash
# Reset mật khẩu Portal + đồng bộ sang Odoo (giống HR reset).
set -euo pipefail
USER_NAME="${1:-Vuonglnt}"
cd /opt/portaljustplay
docker exec portaljustplay-web-1 python manage.py shell -c "
import random, string
from django.contrib.auth.models import User
from hrm.models import Profile
from audit.services.odoo_sync import notify_portal_password_changed

u = User.objects.get(username='${USER_NAME}')
pw = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
u.set_password(pw)
u.save()
notify_portal_password_changed(u, pw)
Profile.require_password_change(u)
p = u.profile
print('username', u.username)
print('odoo_login', u.username)
print('odoo_user_id', p.odoo_user_id)
print('password_synced', p.odoo_password_synced)
print('new_password', pw)
"
