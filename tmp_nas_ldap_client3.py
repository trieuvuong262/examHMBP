#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'ldapx','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())['data']['sid']

def post(sid, **params):
    data = urllib.parse.urlencode({'_sid':sid,**params}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST'), context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())

def api_info(sid):
    q = urllib.parse.urlencode({'_sid':sid,'api':'SYNO.API.Info','version':'1','method':'query','query':'SYNO.Core.Directory.LDAP'})
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/query.cgi?{q}'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())

sid = login()
print('API info:', json.dumps(api_info(sid), indent=2))

# methods from DirectoryServiceCheck
for api, method in [
    ('SYNO.Core.DirectoryServiceCheck.LDAP', 'check'),
    ('SYNO.Core.Directory.LDAP', 'test'),
    ('SYNO.Core.Directory.LDAP', 'check'),
    ('SYNO.Core.Directory.LDAP', 'load'),
]:
    try:
        r = post(sid, api=api, version='1', method=method,
                 host='ldap.justplay.local', base_dn='dc=ldap,dc=justplay,dc=local',
                 bind_dn='uid=root,cn=users,dc=ldap,dc=justplay,dc=local', bind_password=PW)
        print(f'{api}.{method}:', json.dumps(r, ensure_ascii=False)[:400])
    except Exception as e:
        print(f'{api}.{method} ex:', e)

# version 2 set
for ver in ('1', '2'):
    r = post(sid, api='SYNO.Core.Directory.LDAP', version=ver, method='set',
             enable_client='true', is_syno_server='true', host='ldap.justplay.local',
             base_dn='dc=ldap,dc=justplay,dc=local', encryption='no', profile='standard')
    print(f'set v{ver} syno:', json.dumps(r, ensure_ascii=False)[:600])

# external ldap set all fields from get response keys
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
    'enable_idmap': 'true',
    'tls_reqcert': 'false',
    'no_nested_group': 'false',
    'nested_group_level': '0',
    'update_min': '1440',
}
r = post(sid, api='SYNO.Core.Directory.LDAP', version='1', method='set', **fields)
print('full set:', json.dumps(r, ensure_ascii=False)[:800])
