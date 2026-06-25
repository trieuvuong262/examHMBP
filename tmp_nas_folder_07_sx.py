#!/usr/bin/env python3
"""Check NAS shared folder 07_SAN_XUAT permissions vs LDAP group SX."""
import json
import ssl
import urllib.parse
import urllib.request
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'

def admin_login():
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': ADMIN, 'passwd': PW, 'session': 'fs', 'format': 'sid',
        'enable_syno_token': 'yes',
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'),
        context=CTX, timeout=20,
    ) as r:
        p = json.loads(r.read().decode())
    return p['data']['sid'], p['data'].get('synotoken', '')

def post(sid, token, **params):
    q = {'_sid': sid, **params}
    if token:
        q['SynoToken'] = token
    data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    if token:
        req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
        return json.loads(r.read().decode())

sid, token = admin_login()

# List shares
for api, method, ver, extra in [
    ('SYNO.Core.Share', 'list', '1', {}),
    ('SYNO.FileStation.List', 'list_share', '2', {}),
]:
    try:
        r = post(sid, token, api=api, version=ver, method=method, **extra)
        print(f'=== {api}.{method} ===')
        print(json.dumps(r, ensure_ascii=False)[:2500])
    except Exception as e:
        print(api, e)

# Share permission for 07_SAN_XUAT
for method in ['get', 'load_info', 'list_user', 'list_group']:
    try:
        r = post(sid, token, api='SYNO.Core.Share.Permission', version='1', method=method, name='07_SAN_XUAT')
        print(f'=== Share.Permission.{method} ===')
        print(json.dumps(r, ensure_ascii=False)[:2000])
    except Exception as e:
        print('Share.Permission', method, e)

# FileStation list as test-ldap1
def user_login(acct):
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': acct, 'passwd': 'TestLdap@123', 'format': 'sid', 'enable_syno_token': 'yes',
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'),
        context=CTX, timeout=20,
    ) as r:
        p = json.loads(r.read().decode())
    return p

for acct in ['test-ldap1', 'test-ldap1@ldap.justplay.local']:
    r = user_login(acct)
    if not r.get('success'):
        print('user login fail', acct, r.get('error'))
        continue
    usid, utok = r['data']['sid'], r['data'].get('synotoken', '')
    fs = post(usid, utok, api='SYNO.FileStation.List', version='2', method='list_share')
    print(f'=== FileStation shares as {acct} ===')
    shares = fs.get('data', {}).get('shares', [])
    names = [s.get('name') for s in shares]
    print('count', len(names), 'names:', names[:30])
    if '07_SAN_XUAT' in names:
        print('  -> HAS 07_SAN_XUAT')
    else:
        print('  -> NO 07_SAN_XUAT')

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
cmds = [
    'ls -la /volume1/ | head -30',
    'ls -la /volume1/07_SAN_XUAT 2>/dev/null | head -5',
    "synoshare --enum ALL 2>/dev/null | head -40",
    "synoshare --get 07_SAN_XUAT 2>/dev/null",
]
for cmd in cmds:
    full = f"echo '{PW}' | sudo -S bash -c {repr(cmd)} 2>&1"
    _, o, e = c.exec_command(full, timeout=60)
    out = (o.read() + e.read()).decode(errors='replace')
    print('---', cmd[:60])
    print(out[:1500].strip())
c.close()
