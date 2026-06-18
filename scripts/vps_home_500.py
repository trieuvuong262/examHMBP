from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
u = User.objects.filter(username='tp.tb').first()
c = Client(HTTP_HOST='portal.justplay.vn')
c.force_login(u)
try:
    from assessment.portal_widgets import get_portal_dashboard
    w = get_portal_dashboard(u)
    print('widgets OK', len(w))
except Exception as e:
    print('ERROR:', type(e).__name__, e)

r = c.get('/')
print('GET /', r.status_code)
if r.status_code >= 500:
    print(r.content.decode('utf-8', errors='replace')[:800])
