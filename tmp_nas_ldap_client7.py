#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'ds','format':'sid','enable_syno_token':'yes'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    return p['data']['sid'], p.get('data',{}).get('synotoken','')

def post(sid, token, **params):
    q = {'_sid': sid, **params}
    if token: q['SynoToken'] = token
    data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    if token: req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())

sid, token = login()
for method in ['get','set','join','save','apply','enable','disable','status','load','client_set','client_get','client_join']:
    try:
        r = post(sid, token, api='SYNO.DirectoryServer.Server', version='1', method=method,
                 client_enable='true', client_host='ldap.justplay.local', server_enable='true',
                 fqdn='ldap.justplay.local', root_pw=PW, root_pw_confirm=PW)
        code = (r.get('error') or {}).get('code')
        if code != 103:
            print('DS.Server.'+method, json.dumps(r, ensure_ascii=False)[:350])
    except Exception as e:
        print('DS.Server.'+method, e)

# try LDAP set only enable_client false first with host only
for partial in [
    {'host':'ldap.justplay.local'},
    {'host':'ldap.justplay.local','base_dn':'dc=ldap,dc=justplay,dc=local'},
]:
    r = post(sid, token, api='SYNO.Core.Directory.LDAP', version='2', method='set', **partial)
    print('partial set', partial, json.dumps(r, ensure_ascii=False)[:200])
