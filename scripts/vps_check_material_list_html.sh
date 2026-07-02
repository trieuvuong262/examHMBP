#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell -c "
from django.test import Client
from django.contrib.auth import get_user_model
u = get_user_model().objects.filter(is_superuser=True).first()
c = Client()
c.force_login(u)
r = c.get('/kho-npl/danh-muc/', HTTP_HOST='portal.justplay.vn')
html = r.content.decode('utf-8', errors='replace')
print('HTTP', r.status_code)
print('optgroups', html.count('<optgroup'))
print('has category_parent col', 'data-col=\"category_parent\"' in html)
print('has Vải optgroup', 'label=\"Vải\"' in html)
print('has nl-vai optgroup', 'label=\"VẢI\"' in html)
"
