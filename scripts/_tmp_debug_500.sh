#!/usr/bin/env bash
set -euo pipefail
docker exec -i portaljustplay-web-1 python manage.py shell <<'PY'
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

print('ALLOWED_HOSTS', settings.ALLOWED_HOSTS)
User = get_user_model()
u = User.objects.filter(is_active=True, is_superuser=True).first()
print('user', u)
c = Client(HTTP_HOST=settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost')
c.force_login(u)
try:
    r = c.get('/', follow=False)
    print('status', r.status_code)
    if r.status_code >= 400:
        print(r.content[:3000].decode('utf-8', 'replace'))
except Exception:
    import traceback
    traceback.print_exc()

# Also try rendering template with context processors
from django.template.loader import get_template
from django.template import RequestContext
from django.test import RequestFactory
rf = RequestFactory()
req = rf.get('/')
req.user = u
from django.contrib.sessions.middleware import SessionMiddleware
SessionMiddleware(lambda r: None).process_request(req)
req.session.save()
try:
    from assessment.portal_tools import get_portal_tool_groups, get_portal_dashboard
    ctx = {
        'portal_tool_groups': get_portal_tool_groups(),
        'dashboard_widgets': get_portal_dashboard(u),
        'request': req,
    }
    html = get_template('portal.html').render(ctx, req)
    print('template ok', len(html))
except Exception:
    import traceback
    traceback.print_exc()
PY
