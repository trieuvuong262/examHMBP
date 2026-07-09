"""Test endpoint tải RaiDrive trên VPS."""
import os
import sys

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from nas_storage.raidrive_installer_cache import get_ready_raidrive_path
from nas_storage.share_access import get_active_share
from django.conf import settings

token = settings.NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN
share = get_active_share(token)
print('share', share.item_name if share else None, share.rel_path if share else None)
ready = get_ready_raidrive_path(share.item_name) if share else None
print('ready', ready, ready.stat().st_size if ready else None)

u = User.objects.filter(is_active=True, is_superuser=True).first() or User.objects.filter(is_active=True).first()
c = Client()
c.force_login(u)
url = reverse('documents:nas_download_raidrive')
print('url', url)
try:
    r = c.get(url)
    print('status', r.status_code)
    print('content-type', r.get('Content-Type'))
    print('content-length', r.get('Content-Length'))
    print('disposition', r.get('Content-Disposition'))
    if r.status_code >= 400:
        print('body', r.content[:800])
except Exception as exc:
    print('EXCEPTION', type(exc).__name__, exc)
