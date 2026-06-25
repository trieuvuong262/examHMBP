#!/usr/bin/env python3
"""Probe Directory Server package + APIs on Synology NAS."""
import json
import ssl
import urllib.parse
import urllib.request

HOST = '100.93.5.42'
ADMIN = 'admin'
PW = '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()


def login():
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': ADMIN, 'passwd': PW, 'session': 'dsprobe', 'format': 'sid',
    }).encode()
    req = urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST')
    with urllib.request.urlopen(req, context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    if not p.get('success'):
        raise SystemExit(p)
    return p['data']['sid']


def get(sid, api, method, version=1, **params):
    q = {'api': api, 'version': str(version), 'method': method, '_sid': sid, **params}
    url = f"{BASE}/webapi/entry.cgi?{urllib.parse.urlencode(q)}"
    with urllib.request.urlopen(urllib.request.Request(url), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())


def post(sid, api, method, version=1, **params):
    q = {'api': api, 'version': str(version), 'method': method, '_sid': sid}
    q.update(params)
    data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        return json.loads(r.read().decode())


sid = login()
print('login OK')

# Installed packages
for q in ('DirectoryServer', 'LDAPServer', 'directory'):
    try:
        info = get(sid, 'SYNO.Core.Package', 'list', 2)
        pkgs = [p for p in info.get('data', {}).get('packages', []) if q.lower() in p.get('id', '').lower() or q.lower() in p.get('name', '').lower()]
        if pkgs:
            print('packages match', q, json.dumps(pkgs, indent=2)[:800])
    except Exception as e:
        print('package list err', e)

info = get(sid, 'SYNO.Core.Package', 'list', 2)
all_pkgs = info.get('data', {}).get('packages', [])
ds = [p for p in all_pkgs if 'directory' in (p.get('id', '') + p.get('name', '')).lower() or 'ldap' in (p.get('id', '') + p.get('name', '')).lower()]
print('\n=== LDAP/Directory packages ===')
for p in ds:
    print(p.get('id'), p.get('name'), 'installed=', p.get('installed'), 'status=', p.get('status'))

# Directory server APIs
apis = [
    ('SYNO.DirectoryServer', 'get', 1),
    ('SYNO.DirectoryServer', 'get_status', 1),
    ('SYNO.DirectoryServer.Info', 'get', 1),
    ('SYNO.Core.Directory.LDAP', 'get', 1),
    ('SYNO.Core.Directory.LDAP.Profile', 'get', 1),
]
for api, method, ver in apis:
    try:
        p = get(sid, api, method, ver)
        print(f'\n{api}.{method}:', json.dumps(p, ensure_ascii=False)[:600])
    except Exception as e:
        print(f'\n{api}.{method}: ERR {e}')

# API info for DirectoryServer
try:
    qi = get(sid, 'SYNO.API.Info', 'query', 1, query='SYNO.DirectoryServer')
    print('\nAPI.Info DirectoryServer:', json.dumps(qi, indent=2)[:1000])
except Exception as e:
    print('API.Info err', e)
