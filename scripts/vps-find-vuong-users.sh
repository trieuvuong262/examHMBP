#!/usr/bin/env bash
cd /opt/portaljustplay
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.contrib.auth.models import User
for u in User.objects.filter(username__icontains='vuong').select_related('profile'):
    p = u.profile
    print(u.username, u.email, p.odoo_user_id, p.is_employed)
"
