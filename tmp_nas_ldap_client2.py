#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()
FQDN = 'ldap.justplay.local'
LDAP_BASE = 'dc=ldap,dc=justplay,dc=local'
BIND_DN = 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local'

def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'fix','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())['data']['sid']

def post(sid, **params):
    data = urllib.parse.urlencode({'_sid':sid,**params}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST'), context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())

def get(sid, api, method):
    q = urllib.parse.urlencode({'_sid':sid,'api':api,'version':'1','method':method})
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi?{q}'), context=CTX, timeout=30) as r:
        return json.loads(r.read().decode())

sid = login()
print('BEFORE server:', get(sid,'SYNO.DirectoryServer.Server','get').get('data',{}).get('server_enable'))

# 1) Re-enable LDAP server
r = post(sid, api='SYNO.DirectoryServer.Server', version='1', method='set',
         server_enable='true', fqdn=FQDN, root_pw=PW, root_pw_confirm=PW)
print('re-enable server:', r.get('success'), json.dumps(r.get('data',{}), ensure_ascii=False)[:400] if r.get('success') else r.get('error'))

import time
time.sleep(8)
print('AFTER server:', get(sid,'SYNO.DirectoryServer.Server','get').get('data',{}))

# 2) LDAP client - try is_syno_server + enable_client
ldap_payloads = [
    {'enable_client':'true','is_syno_server':'true','host':FQDN,'base_dn':LDAP_BASE,'encryption':'no','profile':'standard','ldap_schema':'rfc2307'},
    {'enable_client':'true','is_syno_server':'true','host':'127.0.0.1','base_dn':LDAP_BASE,'encryption':'no','profile':'standard'},
    {'enable_client':'true','host':HOST,'base_dn':LDAP_BASE,'bind_dn':BIND_DN,'bind_password':PW,'encryption':'no','profile':'standard','enable_cifs':'true','enable_cifs_pam':'true'},
    {'enable_client':'true','host':FQDN,'base_dn':LDAP_BASE,'bind_dn':BIND_DN,'password':PW,'encryption':'no','profile':'standard','enable_cifs':'true'},
    {'enable_client':'true','host':FQDN,'base_dn':LDAP_BASE,'bind_dn':BIND_DN,'bind_pw':PW,'bind_pw_confirm':PW,'encryption':'no'},
]
for p in ldap_payloads:
    r = post(sid, api='SYNO.Core.Directory.LDAP', version='1', method='set', **p)
    code = (r.get('error') or {}).get('code')
    print('LDAP.set', sorted(p.keys()), '->', 'OK' if r.get('success') else f'err {code}', json.dumps(r, ensure_ascii=False)[:500])

print('\nLDAP get:', json.dumps(get(sid,'SYNO.Core.Directory.LDAP','get'), ensure_ascii=False)[:1200])

# test bind ldap still works
try:
    import ldap
    c = ldap.initialize(f'ldap://{HOST}:389')
    c.set_option(ldap.OPT_REFERRALS, ldap.OPT_OFF)
    c.simple_bind_s(BIND_DN, PW)
    res = c.search_s(LDAP_BASE, ldap.SCOPE_SUBTREE, '(uid=test-ldap)', ['uid'])
    c.unbind_s()
    print('LDAP bind test:', len(res), 'user(s)')
except Exception as e:
    print('LDAP bind test FAIL', e)

# DSM login tests
for user, pwd in [('test-ldap','TestLdap@123'),('admin',PW)]:
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':user,'passwd':pwd,'session':'t','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    print(f'DSM login {user}:', 'OK' if p.get('success') else p.get('error'))
