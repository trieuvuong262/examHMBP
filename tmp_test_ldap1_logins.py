#!/usr/bin/env python3
"""Kiểm tra login test-ldap1 trên Portal, Odoo, NAS."""
import json
import os
import ssl
import urllib.parse
import urllib.request
import xmlrpc.client

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import authenticate

USERNAME = 'test-ldap1'
PASSWORD = 'TestLdap@123'
NAS_HOST = '100.93.5.42'
LDAP_BASE = 'dc=ldap,dc=justplay,dc=local'
BIND_DN = 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local'
BIND_PW = '123123sS@@'
CTX = ssl._create_unverified_context()
BASE = f'https://{NAS_HOST}:5556'

print('Portal auth:', bool(authenticate(username=USERNAME, password=PASSWORD)))

from django.conf import settings

url = settings.ODOO_URL.rstrip('/')
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(settings.ODOO_DB, USERNAME, PASSWORD, {})
print('Odoo uid:', uid)

try:
    from ldap3 import Connection, Server, Tls

    tls = Tls(validate=ssl.CERT_NONE)
    server = Server(NAS_HOST, port=636, use_ssl=True, tls=tls)
    conn = Connection(server, user=BIND_DN, password=BIND_PW, auto_bind=True)
    conn.search(
        f'cn=users,{LDAP_BASE}',
        f'(uid={USERNAME})',
        attributes=['uid', 'cn', 'memberOf'],
    )
    print('LDAP entry:', conn.entries[0].entry_dn if conn.entries else 'NOT FOUND')
    conn.search(f'cn=groups,{LDAP_BASE}', f'(memberUid={USERNAME})', attributes=['cn'])
    groups = [str(e.cn) for e in conn.entries]
    print('LDAP groups:', groups)
    conn.unbind()
except Exception as exc:
    print('LDAP check error:', exc)

for account in [f'{USERNAME}@ldap.justplay.local', USERNAME]:
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth',
        'version': '7',
        'method': 'login',
        'account': account,
        'passwd': PASSWORD,
        'format': 'sid',
        'enable_syno_token': 'yes',
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'),
        context=CTX,
        timeout=20,
    ) as r:
        res = json.loads(r.read().decode())
    print('NAS DSM', account, '->', 'OK' if res.get('success') else res.get('error'))
