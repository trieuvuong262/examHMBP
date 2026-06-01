import os
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()
print('user:', user)
client = Client()
client.force_login(user)
for path in ('/thiet-bi/', '/thiet-bi/danh-sach/', '/thiet-bi/nhap-excel/'):
    try:
        resp = client.get(path)
        print(path, resp.status_code)
        if resp.status_code >= 500:
            print(resp.content.decode('utf-8', errors='replace')[:3000])
    except Exception:
        traceback.print_exc()
