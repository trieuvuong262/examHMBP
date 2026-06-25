#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST = '100.93.5.42'
CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'

def login(account, passwd, session=None):
    p = {'api':'SYNO.API.Auth','version':'7','method':'login','account':account,'passwd':passwd,'format':'sid','enable_syno_token':'yes'}
    if session is not None:
        p['session'] = session
    data = urllib.parse.urlencode(p).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())

for acct in ['test-ldap@ldap.justplay.local', 'test-ldap']:
    r = login(acct, 'TestLdap@123', session=None)
    print('LOGIN', acct, '->', 'OK sid='+r['data']['sid'][:8]+'...' if r.get('success') else r.get('error'))
    if r.get('success'):
        sid, token = r['data']['sid'], r['data'].get('synotoken','')
        q = urllib.parse.urlencode({'_sid':sid,'SynoToken':token,'api':'SYNO.Core.System','version':'3','method':'info'}).encode()
        req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=q, method='POST')
        if token: req.add_header('X-SYNO-TOKEN', token)
        with urllib.request.urlopen(req, context=CTX, timeout=20) as resp:
            info = json.loads(resp.read().decode())
        print('  System.info ->', 'OK' if info.get('success') else info.get('error'))
