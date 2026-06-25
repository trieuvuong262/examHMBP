#!/usr/bin/env python3
"""Diag LDAP group SX vs NAS cache for test users."""
import json
import os
import ssl
import urllib.parse
import urllib.request

import django
import paramiko

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth.models import User

from audit.services.nas_ldap_sync import nas_ldap_group_for_department, provision_ldap_user

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
LDAP_BASE = 'dc=ldap,dc=justplay,dc=local'
BIND_DN = 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local'
BIND_PW = '123123sS@@'
CTX = ssl._create_unverified_context()

try:
    from ldap3 import Connection, Server, Tls

    tls = Tls(validate=ssl.CERT_NONE)
    server = Server(HOST, port=636, use_ssl=True, tls=tls)
    conn = Connection(server, user=BIND_DN, password=BIND_PW, auto_bind=True)

    def ldap_groups(uid):
        conn.search(f'cn=groups,{LDAP_BASE}', f'(memberUid={uid})', attributes=['cn'])
        return sorted(str(e.cn) for e in conn.entries)

    for username in ['test-ldap', 'test-ldap1']:
        u = User.objects.select_related('profile__department').filter(username=username).first()
        if not u:
            print(username, 'NOT IN PORTAL')
            continue
        dept = u.profile.department.name if u.profile and u.profile.department else None
        expected = nas_ldap_group_for_department(dept)
        groups = ldap_groups(username)
        print(f'=== {username} ===')
        print('  Portal dept:', repr(dept), '-> expected LDAP:', expected)
        print('  LDAP memberUid groups:', groups)
        if expected and expected not in groups:
            print('  FIX: re-provision...')
            print(' ', provision_ldap_user(u, password=None))
            print('  After fix:', ldap_groups(username))
    conn.unbind()
except Exception as exc:
    print('LDAP error:', exc)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
for u in ['test-ldap', 'test-ldap1']:
    _, o, _ = c.exec_command(
        f"echo '{PW}' | sudo -S grep -i '^{u}@' /usr/syno/etc/private/ldap_user 2>/dev/null",
        timeout=60,
    )
    print(f'NAS cache {u}:', (o.read()).decode(errors='replace').strip() or '(missing)')
_, o, _ = c.exec_command(
    f"echo '{PW}' | sudo -S ldapsearch -x -H ldap://127.0.0.1 -b 'cn=groups,{LDAP_BASE}' -D '{BIND_DN}' -w '{BIND_PW}' '(cn=SX)' memberUid 2>/dev/null | grep -E 'memberUid:|^#' | tail -20",
    timeout=60,
)
print('LDAP SX tail members:', (o.read()).decode(errors='replace')[:1500])
c.close()
