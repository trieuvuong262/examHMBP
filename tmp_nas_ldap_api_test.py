#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, CTX = '100.93.5.42', ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'
data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':'test-ldap@ldap.justplay.local','passwd':'TestLdap@123','format':'sid','enable_syno_token':'yes'}).encode()
with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
    p = json.loads(r.read().decode())
sid, token = p['data']['sid'], p['data'].get('synotoken','')
for api, method in [('SYNO.API.Info','query'), ('SYNO.Core.Desktop.Initdata','get'), ('SYNO.FileStation.List','list_share')]:
    q = urllib.parse.urlencode({'_sid':sid,'SynoToken':token,'api':api,'version':'1','method':method}).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=q, method='POST')
    if token: req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=20) as resp:
        res = json.loads(resp.read().decode())
    print(api, '->', 'OK' if res.get('success') else res.get('error'))
