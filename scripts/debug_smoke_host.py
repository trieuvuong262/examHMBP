import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

u = get_user_model().objects.filter(is_superuser=True).first()
c = Client()
c.force_login(u)
url = reverse('kho_npl:material_list')
for host in ['portal.justplay.vn', 'localhost', 'testserver'] + list(settings.ALLOWED_HOSTS[:3]):
    r = c.get(url, HTTP_HOST=host)
    print(host, r.status_code)
print('ALLOWED', settings.ALLOWED_HOSTS)
