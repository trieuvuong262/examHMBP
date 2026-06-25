#!/usr/bin/env python3
import json
import ssl
import urllib.parse
import urllib.request

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()
FQDN = 'ldap.justplay.local'
LDAP_ADMIN_PW = PW  # bind DN password per Synology wizard


def login():
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': ADMIN, 'passwd': PW, 'session': 'dssrv', 'format': 'sid',
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    return p['data']['sid']


def call(sid, api, method, version=1, post=False, **params):
    q = {'api': api, 'version': str(version), 'method': method, '_sid': sid}
    q.update(params)
    if post:
        data = urllib.parse.urlencode(q).encode()
        req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    else:
        req = urllib.request.Request(f'{BASE}/webapi/entry.cgi?{urllib.parse.urlencode(q)}')
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        return json.loads(r.read().decode())


sid = login()
print('login OK')

for api, method in [
    ('SYNO.DirectoryServer.Server', 'get'),
    ('SYNO.DirectoryServer.Server', 'load'),
    ('SYNO.DirectoryServer.Server', 'status'),
    ('SYNO.DirectoryServer.DB', 'get'),
    ('SYNO.DirectoryServer.Group', 'list'),
]:
    try:
        r = call(sid, api, method)
        print(f'{api}.{method}:', json.dumps(r, ensure_ascii=False)[:900])
    except Exception as ex:
        print(f'{api}.{method}: ERR {ex}')

# Try enable server
payloads = [
    {'enable': 'true', 'fqdn': FQDN, 'password': LDAP_ADMIN_PW},
    {'enabled': 'true', 'fqdn': FQDN, 'admin_password': LDAP_ADMIN_PW},
    {'enable_server': 'true', 'fqdn': FQDN, 'password': LDAP_ADMIN_PW},
]
for method in ('set', 'save', 'apply', 'enable'):
    for p in payloads:
        try:
            r = call(sid, 'SYNO.DirectoryServer.Server', method, post=True, **p)
            if r.get('success') or r.get('error', {}).get('code') not in (102, 103):
                print(f'Server.{method}', list(p.keys()), '->', json.dumps(r, ensure_ascii=False)[:500])
        except Exception as ex:
            print(f'Server.{method} ex', ex)

r = call(sid, 'SYNO.DirectoryServer.Server', 'get')
print('final Server.get:', json.dumps(r, ensure_ascii=False)[:800])
r2 = call(sid, 'SYNO.Core.Directory.LDAP', 'get')
print('final LDAP.get:', json.dumps(r2, ensure_ascii=False)[:500])
