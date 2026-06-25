#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login_token():
    data = urllib.parse.urlencode({
        'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,
        'session':'Core','format':'sid','enable_syno_token':'yes',
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    return p['data']['sid'], p['data'].get('synotoken', '')

def post(sid, synotoken, **params):
    q = {'_sid': sid, **params}
    if synotoken:
        q['SynoToken'] = synotoken
    data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    if synotoken:
        req.add_header('X-SYNO-TOKEN', synotoken)
    with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())

sid, token = login_token()
print('token', token[:20] if token else None)

fields = {
    'enable_client': 'true',
    'host': 'ldap.justplay.local',
    'base_dn': 'dc=ldap,dc=justplay,dc=local',
    'bind_dn': 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local',
    'bind_password': PW,
    'encryption': 'no',
    'profile': 'standard',
    'ldap_schema': 'rfc2307',
    'enable_cifs': 'true',
    'enable_cifs_pam': 'true',
}
for ver in ('1','2'):
    r = post(sid, token, api='SYNO.Core.Directory.LDAP', version=ver, method='set', **fields)
    print(f'set v{ver}:', json.dumps(r, ensure_ascii=False)[:500])

r = post(sid, token, api='SYNO.Core.Directory.LDAP', version='1', method='get')
print('get:', json.dumps(r, ensure_ascii=False)[:600])

# login test
for user, pwd in [('test-ldap','TestLdap@123'),]:
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':user,'passwd':pwd,'session':'t','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    print('DSM', user, 'OK' if p.get('success') else p.get('error'))
