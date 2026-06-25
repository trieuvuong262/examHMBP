#!/usr/bin/env python3
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from audit.services.nas_ldap_sync import provision_ldap_user
from django.contrib.auth.models import User

for username in ['test-ldap', 'test-ldap1']:
    u = User.objects.get(username=username)
    r = provision_ldap_user(u)
    print(username, r)
