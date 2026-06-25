#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'

def login():
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': ADMIN, 'passwd': PW, 'format': 'sid', 'enable_syno_token': 'yes',
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    return p['data']['sid'], p['data'].get('synotoken', '')

def call(sid, token, api, method, version='1', **p):
    q = {'_sid': sid, 'api': api, 'version': version, 'method': method, **p}
    if token:
        q['SynoToken'] = token
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=urllib.parse.urlencode(q).encode(), method='POST')
    if token:
        req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
        return json.loads(r.read().decode())

sid, token = login()
qi = call(sid, token, 'SYNO.API.Info', 'query', version='1', query='all')
for k in sorted(qi.get('data', {})):
    if 'Share' in k or 'ACL' in k or 'Privilege' in k:
        print(k, qi['data'][k])

# try share permission APIs
for ver in ['1', '2', '3']:
    for method in ['get', 'load', 'list', 'enum']:
        try:
            r = call(sid, token, 'SYNO.Core.Share.Permission', method, version=ver, name='07_SAN_XUAT')
            if r.get('success') or r.get('error', {}).get('code') != 103:
                print(f'Permission v{ver} {method}:', json.dumps(r, ensure_ascii=False)[:1200])
        except Exception as e:
            pass

# Compare with 05_MARKETING (admin sees it)
for share in ['07_SAN_XUAT', '05_MARKETING', 'docker']:
    for ver in ['1', '2']:
        try:
            r = call(sid, token, 'SYNO.Core.Share.Permission', 'get', version=ver, name=share)
            print(f'get {share} v{ver}:', json.dumps(r, ensure_ascii=False)[:800])
        except Exception:
            pass

# FileStation as a known SX LDAP user from member list - try DNhu
for acct, pwd in [('DNhu', 'justplay@123'), ('test-ldap1', 'TestLdap@123')]:
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': acct, 'passwd': pwd, 'format': 'sid', 'enable_syno_token': 'yes',
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    if not p.get('success'):
        print('login fail', acct, p.get('error'))
        continue
    usid, utok = p['data']['sid'], p['data'].get('synotoken', '')
    fs = call(usid, utok, 'SYNO.FileStation.List', 'list_share', version='2')
    names = [s['name'] for s in fs.get('data', {}).get('shares', [])]
    print(f'{acct} shares ({len(names)}):', names)
