#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'x','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())['data']['sid']

def get(sid, api, method, **p):
    q = urllib.parse.urlencode({'_sid':sid,'api':api,'version':'1','method':method,**p})
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi?{q}'), context=CTX, timeout=30) as r:
        return json.loads(r.read().decode())

sid = login()
qi = get(sid, 'SYNO.API.Info', 'query')
apps = [k for k in qi.get('data',{}) if 'App' in k or 'Portal' in k or 'Privilege' in k or 'ACL' in k]
print('app apis:', apps[:30])

for api in ['SYNO.Core.AppPortal', 'SYNO.Core.AppPortal.Config', 'SYNO.Core.AppPriv', 'SYNO.Core.AppPriv.Role']:
    try:
        r = get(sid, api, 'get')
        print(api, json.dumps(r, ensure_ascii=False)[:400])
    except Exception as e:
        print(api, e)
