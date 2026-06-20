from django.contrib.auth.models import User
from django.test import Client
from django.conf import settings

host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
u = User.objects.get(username='Ductn')
c = Client(HTTP_HOST=host)
c.force_login(u)

resp = c.get('/reports/sx/team/?status=submitted', follow=True)
text = resp.content.decode('utf-8', errors='replace')
print('tr count:', text.count('<tr>'))
print('has tbody rows:', 'Chưa nộp' in text)
# check if table body empty
idx = text.find('<tbody>')
if idx >= 0:
    tbody = text[idx:idx+2000]
    data_rows = tbody.count('<tr>') - tbody.count('table-light')
    print('tbody snippet rows:', tbody.count('<tr>'))
    if 'Không có' in tbody or tbody.count('<tr>') <= 1:
        print('TABLE APPEARS EMPTY')
    print(tbody[:500])
