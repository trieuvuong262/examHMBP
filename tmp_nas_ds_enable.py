#!/usr/bin/env python3
"""Install/start Directory Server + enable LDAP via DSM API."""
import json
import ssl
import time
import urllib.parse
import urllib.request

HOST = '100.93.5.42'
ADMIN, PW = 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()
PKG = 'DirectoryServer'


def req(method, url, data=None):
    r = urllib.request.Request(url, data=data, method=method)
    with urllib.request.urlopen(r, context=CTX, timeout=60) as resp:
        return json.loads(resp.read().decode())


def login():
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': ADMIN, 'passwd': PW, 'session': 'dsenable', 'format': 'sid',
    }).encode()
    p = req('POST', f'{BASE}/webapi/auth.cgi', data)
    if not p.get('success'):
        raise SystemExit(f'login fail: {p}')
    return p['data']['sid']


def api(sid, api_name, method, version=1, post=False, **params):
    q = {'api': api_name, 'version': str(version), 'method': method, '_sid': sid}
    q.update({k: v for k, v in params.items() if v is not None})
    if post:
        data = urllib.parse.urlencode(q).encode()
        return req('POST', f'{BASE}/webapi/entry.cgi', data)
    url = f"{BASE}/webapi/entry.cgi?{urllib.parse.urlencode(q)}"
    return req('GET', url)


sid = login()
print('login OK')

# Package status
for ver in (1, 2):
    st = api(sid, 'SYNO.Core.Package', 'get', ver, id=PKG)
    print(f'package get v{ver}:', json.dumps(st, ensure_ascii=False)[:800])

# Try install (no-op if installed)
ins = api(sid, 'SYNO.Core.Package', 'install', 1, post=True, id=PKG, name='LDAP Server')
print('install:', json.dumps(ins, ensure_ascii=False)[:500])

# Poll install task if started
if ins.get('success') and ins.get('data', {}).get('task_id'):
    tid = ins['data']['task_id']
    for i in range(30):
        time.sleep(3)
        t = api(sid, 'SYNO.Core.Package.Installation', 'status', 1, task_id=tid)
        print('install status', i, json.dumps(t, ensure_ascii=False)[:300])
        if t.get('data', {}).get('finished'):
            break

# Start package
for m in ('start', 'stop'):
    r = api(sid, 'SYNO.Core.Package', m, 1, post=True, id=PKG)
    print(m, json.dumps(r, ensure_ascii=False)[:400])

# Directory Server APIs after start
time.sleep(3)
for api_name, method in (
    ('SYNO.DirectoryServer', 'get'),
    ('SYNO.DirectoryServer', 'get_status'),
    ('SYNO.DirectoryServer.Setting', 'get'),
    ('SYNO.DirectoryServer.Setting', 'load'),
):
    r = api(sid, api_name, method, 1)
    print(f'{api_name}.{method}:', json.dumps(r, ensure_ascii=False)[:700])

# Try enable LDAP server - common parameter names from docs
fqdn = 'ldap.justplay.local'
for payload in (
    {'enable': 'true', 'fqdn': fqdn, 'password': PW},
    {'enable_ldap': 'true', 'fqdn': fqdn, 'admin_password': PW},
):
    for api_name in ('SYNO.DirectoryServer', 'SYNO.DirectoryServer.Setting'):
        for method in ('set', 'save', 'apply'):
            try:
                r = api(sid, api_name, method, 1, post=True, **payload)
                if r.get('success') or r.get('error', {}).get('code') != 103:
                    print(f'try {api_name}.{method}', payload.keys(), '->', json.dumps(r, ensure_ascii=False)[:400])
            except Exception as ex:
                pass

ldap = api(sid, 'SYNO.Core.Directory.LDAP', 'get', 1)
print('ldap get final:', json.dumps(ldap, ensure_ascii=False)[:500])
