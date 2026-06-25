#!/usr/bin/env python3
"""Probe + enable NAS LDAP client (join Directory Server)."""
import json
import ssl
import urllib.parse
import urllib.request

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()
LDAP_HOST = 'ldap.justplay.local'
LDAP_BASE = 'dc=ldap,dc=justplay,dc=local'
BIND_DN = 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local'


def login():
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': ADMIN, 'passwd': PW, 'session': 'ldapcli', 'format': 'sid',
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())['data']['sid']


def call(sid, api, method, post=False, version='1', **params):
    q = {'api': api, 'version': str(version), 'method': method, '_sid': sid, **params}
    if post:
        data = urllib.parse.urlencode(q).encode()
        req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    else:
        req = urllib.request.Request(f'{BASE}/webapi/entry.cgi?{urllib.parse.urlencode(q)}')
    with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())


def api_info(sid, query='all'):
    q = urllib.parse.urlencode({'_sid': sid, 'api': 'SYNO.API.Info', 'version': '1', 'method': 'query', 'query': query})
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/query.cgi?{q}'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())


sid = login()
info = api_info(sid)
apis = [k for k in info.get('data', {}) if 'LDAP' in k or 'Directory' in k]
print('APIs:', apis)

for api, method in [
    ('SYNO.DirectoryServer.Server', 'get'),
    ('SYNO.Core.Directory.LDAP', 'get'),
    ('SYNO.Core.Directory.LDAP.Profile', 'get'),
    ('SYNO.Core.Directory.LDAP.BaseDN', 'get'),
    ('SYNO.Core.Directory.LDAP.Status', 'get'),
]:
    try:
        r = call(sid, api, method)
        print(f'\n{api}.{method}:', json.dumps(r, ensure_ascii=False)[:1200])
    except Exception as e:
        print(f'{api}.{method} ERR', e)

# Try DirectoryServer client enable
payloads = [
    {'client_enable': 'true', 'client_host': LDAP_HOST},
    {'client_enable': 'true', 'client_host': '127.0.0.1'},
    {'client_enable': 'true', 'client_host': HOST},
    {'client_enable': 'true', 'client_host': LDAP_HOST, 'is_join_domain': 'true'},
]
for p in payloads:
    r = call(sid, 'SYNO.DirectoryServer.Server', 'set', post=True, **p)
    print('\nDirectoryServer.set', p, '->', json.dumps(r, ensure_ascii=False)[:800])

# Try Core.Directory.LDAP set variants
ldap_sets = [
    {
        'enable_client': 'true', 'host': LDAP_HOST, 'base_dn': LDAP_BASE,
        'bind_dn': BIND_DN, 'bind_password': PW, 'encryption': 'no', 'profile': 'standard',
    },
    {
        'enable_client': 'true', 'host': HOST, 'base_dn': LDAP_BASE,
        'bind_dn': BIND_DN, 'bind_password': PW, 'encryption': 'no', 'profile': 'standard',
    },
    {
        'enable_client': 'true', 'host': '127.0.0.1', 'base_dn': LDAP_BASE,
        'bind_dn': BIND_DN, 'bind_password': PW, 'encryption': 'no', 'profile': 'standard',
    },
]
for p in ldap_sets:
    for method in ('set', 'save', 'apply'):
        try:
            r = call(sid, 'SYNO.Core.Directory.LDAP', method, post=True, **p)
            if r.get('success') or r.get('error', {}).get('code') not in (102, 103):
                print(f'\nLDAP.{method}', list(p.keys()), '->', json.dumps(r, ensure_ascii=False)[:900])
        except Exception as e:
            print(f'LDAP.{method} ex', e)

print('\n=== FINAL ===')
print('Server:', json.dumps(call(sid, 'SYNO.DirectoryServer.Server', 'get'), ensure_ascii=False)[:1000])
print('LDAP:', json.dumps(call(sid, 'SYNO.Core.Directory.LDAP', 'get'), ensure_ascii=False)[:1000])

# test DSM login test-ldap
for user, pwd in [('test-ldap', 'TestLdap@123'), ('admin', PW)]:
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': user, 'passwd': pwd, 'session': 't', 'format': 'sid',
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    print(f'login {user}:', 'OK' if p.get('success') else p.get('error'))
