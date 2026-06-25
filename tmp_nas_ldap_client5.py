#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'Core','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())['data']['sid']

def post(sid, **params):
    data = urllib.parse.urlencode({'_sid':sid,**params}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST'), context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())

def get(sid, api, method, **extra):
    q = urllib.parse.urlencode({'_sid':sid,'api':api,'version':'1','method':method,**extra})
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi?{q}'), context=CTX, timeout=30) as r:
        return json.loads(r.read().decode())

sid = login()

# list available methods by brute force common names on LDAP
for method in ['get','set','save','apply','join','enable','disable','test','check','list','load','start']:
    r = post(sid, api='SYNO.Core.Directory.LDAP', version='1', method=method)
    code = (r.get('error') or {}).get('code')
    if code not in (103,):
        print(f'LDAP.{method}:', json.dumps(r, ensure_ascii=False)[:200])

for method in ['get','set','list','join','save']:
    r = post(sid, api='SYNO.Core.Directory.LDAP.Profile', version='1', method=method)
    code = (r.get('error') or {}).get('code')
    if code not in (103,):
        print(f'Profile.{method}:', json.dumps(r, ensure_ascii=False)[:300])

# profile set with profiles json
profile = {
    'host': 'ldap.justplay.local',
    'base_dn': 'dc=ldap,dc=justplay,dc=local',
    'bind_dn': 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local',
    'bind_password': PW,
    'encryption': 'no',
    'enable_client': True,
}
for key in ('profile', 'profiles', 'data', 'conf'):
    r = post(sid, api='SYNO.Core.Directory.LDAP.Profile', version='1', method='set', **{key: json.dumps(profile)})
    print(f'Profile.set {key}=', json.dumps(r, ensure_ascii=False)[:300])

# Domain join API
for api in ['SYNO.Core.Directory.Domain','SYNO.Core.Directory.Domain.Conf']:
    r = get(sid, api, 'get')
    print(api, json.dumps(r, ensure_ascii=False)[:400])
