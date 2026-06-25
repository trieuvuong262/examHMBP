#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST = '100.93.5.42'
CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'
ACCT, PWD = 'test-ldap@ldap.justplay.local', 'TestLdap@123'

for session in ['t', 'DSM', 'Core', '']:
    p = {'api':'SYNO.API.Auth','version':'7','method':'login','account':ACCT,'passwd':PWD,'format':'sid'}
    if session:
        p['session'] = session
    data = urllib.parse.urlencode(p).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        res = json.loads(r.read().decode())
    print('session=%r ->' % session, 'OK' if res.get('success') else res.get('error'))
