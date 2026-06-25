#!/usr/bin/env python3
import json
import ssl
import urllib.parse
import urllib.request

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

data = urllib.parse.urlencode({
    'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
    'account': ADMIN, 'passwd': PW, 'session': 'apiinfo', 'format': 'sid',
}).encode()
with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
    sid = json.loads(r.read().decode())['data']['sid']

q = urllib.parse.urlencode({'api': 'SYNO.API.Info', 'version': '1', 'method': 'query', 'query': 'all', '_sid': sid})
with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi?{q}'), context=CTX, timeout=30) as r:
    apis = json.loads(r.read().decode()).get('data', {})

hits = {k: v for k, v in apis.items() if 'directory' in k.lower() or 'ldap' in k.lower()}
for k in sorted(hits):
    print(k, hits[k])
