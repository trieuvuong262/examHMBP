import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

from hrm.module_permissions import MODULE_DE_XUAT, user_can_access_module
from service_requests.access import user_can_access_flow
from service_requests.flow import FLOW_DE_XUAT

User = get_user_model()
PATH = '/yeu-cau/de-xuat/cua-toi/'

for user in User.objects.filter(is_active=True).order_by('username'):
    can_mod = user_can_access_module(user, MODULE_DE_XUAT)
    can_flow = user_can_access_flow(user, FLOW_DE_XUAT)
    client = Client(HTTP_HOST='portal.justplay.vn')
    client.force_login(user)
    r = client.get(PATH, follow=False)
    loc = r.get('Location', '')
    print(f'{user.username:12} mod={can_mod} flow={can_flow} -> {r.status_code} {loc}')
