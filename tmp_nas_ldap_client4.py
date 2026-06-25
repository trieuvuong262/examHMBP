#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login(session='Core'):
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': ADMIN, 'passwd': PW, 'session': session, 'format': 'sid',
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    if not p.get('success'):
        raise SystemExit(f'login fail {session}: {p}')
    return p['data']['sid']

def post(sid, **params):
    data = urllib.parse.urlencode({'_sid': sid, **params}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST'), context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())

for sess in ['Core', 'SYNO.Core.Directory.LDAP', 'Directory', 'DSM']:
    sid = login(sess)
    r = post(sid, api='SYNO.Core.Directory.LDAP', version='2', method='set',
             enable_client='true', host='ldap.justplay.local', base_dn='dc=ldap,dc=justplay,dc=local',
             bind_dn='uid=root,cn=users,dc=ldap,dc=justplay,dc=local', bind_password=PW,
             encryption='no', profile='standard', ldap_schema='rfc2307')
    print('session', sess, '->', json.dumps(r, ensure_ascii=False)[:300])

# DirectoryServer combined server+client
sid = login('DirectoryServer')
for payload in [
    {'server_enable':'true','client_enable':'true','fqdn':'ldap.justplay.local','client_host':'127.0.0.1','root_pw':PW,'root_pw_confirm':PW},
    {'server_enable':'true','client_enable':'true','fqdn':'ldap.justplay.local','client_host':'ldap.justplay.local','root_pw':PW,'root_pw_confirm':PW,'is_join_domain':'true'},
]:
    r = post(sid, api='SYNO.DirectoryServer.Server', version='1', method='set', **payload)
    print('DS.set', payload.keys(), '->', json.dumps(r.get('data', r.get('error')), ensure_ascii=False)[:400])
