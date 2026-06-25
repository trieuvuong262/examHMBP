#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'x','format':'sid','enable_syno_token':'yes'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    return p['data']['sid'], p['data'].get('synotoken','')

def call(sid, token, api, method, post=False, version='1', **p):
    q = {'_sid':sid,'api':api,'version':version,'method':method,**p}
    if token: q['SynoToken']=token
    if post:
        data = urllib.parse.urlencode(q).encode()
        req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    else:
        req = urllib.request.Request(f'{BASE}/webapi/entry.cgi?{urllib.parse.urlencode(q)}')
    if token: req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
        return json.loads(r.read().decode())

sid, token = login()
for method in ['get','list','load','save','set']:
    try:
        r = call(sid, token, 'SYNO.Core.AppPortal.AccessControl', method)
        print('AccessControl.'+method, json.dumps(r, ensure_ascii=False)[:500])
    except Exception as e:
        print('AccessControl.'+method, e)

for method in ['get','list','set']:
    try:
        r = call(sid, token, 'SYNO.Core.AppPriv.App', method)
        print('AppPriv.App.'+method, json.dumps(r, ensure_ascii=False)[:500])
    except Exception as e:
        print('AppPriv.App.'+method, e)
