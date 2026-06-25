#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request

HOST = '100.93.5.42'
CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'

def login(acct, pwd):
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': acct, 'passwd': pwd, 'format': 'sid', 'enable_syno_token': 'yes',
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'),
        context=CTX, timeout=20,
    ) as r:
        return json.loads(r.read().decode())

def fs_list(sid, token):
    q = urllib.parse.urlencode({
        '_sid': sid, 'SynoToken': token,
        'api': 'SYNO.FileStation.List', 'version': '2', 'method': 'list_share',
    }).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=q, method='POST')
    req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        return json.loads(r.read().decode())

for acct in ['test-ldap1', 'test-ldap1@ldap.justplay.local']:
    r = login(acct, 'TestLdap@123')
    if not r.get('success'):
        print(acct, 'login fail', r.get('error'))
        continue
    sid, token = r['data']['sid'], r['data'].get('synotoken', '')
    fs = fs_list(sid, token)
    names = sorted(s.get('name') for s in fs.get('data', {}).get('shares', []))
    print(acct, 'shares:', names)
    print('  has 07_SAN_XUAT:', '07_SAN_XUAT' in names)
