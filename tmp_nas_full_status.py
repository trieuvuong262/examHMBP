#!/usr/bin/env python3
"""Verify NAS LDAP client + full login matrix."""
import json, ssl, urllib.parse, urllib.request
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()
LDAP_PW = '123123sS@@'

def dsm_login(account, passwd):
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': account, 'passwd': passwd, 'session': 't', 'format': 'sid',
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'),
        context=CTX, timeout=20,
    ) as r:
        return json.loads(r.read().decode())

def admin_api(sid, token, api, method, **p):
    q = {'_sid': sid, 'api': api, 'version': '1', 'method': method, **p}
    if token:
        q['SynoToken'] = token
    data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    if token:
        req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
        return json.loads(r.read().decode())

# admin login for status
data = urllib.parse.urlencode({
    'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
    'account': ADMIN, 'passwd': PW, 'session': 'x', 'format': 'sid',
    'enable_syno_token': 'yes',
}).encode()
with urllib.request.urlopen(
    urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'),
    context=CTX, timeout=20,
) as r:
    ap = json.loads(r.read().decode())
sid, token = ap['data']['sid'], ap['data'].get('synotoken', '')

ldap_get = admin_api(sid, token, 'SYNO.Core.Directory.LDAP', 'get', version='2')
ds_get = admin_api(sid, token, 'SYNO.DirectoryServer.Server', 'get')
print('=== LDAP client status ===')
print(json.dumps(ldap_get.get('data', ldap_get), indent=2, ensure_ascii=False)[:1200])
print('=== Directory Server ===')
print(json.dumps(ds_get.get('data', ds_get), indent=2, ensure_ascii=False)[:800])

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

cmds = [
    f"echo '{PW}' | sudo -S test -f /usr/syno/etc/ldapclient/ldap_joined && echo JOINED_OK || echo NOT_JOINED",
    f"echo '{PW}' | sudo -S wc -l /usr/syno/etc/private/ldap_user",
    f"echo '{PW}' | sudo -S grep -i test-ldap /usr/syno/etc/private/ldap_user | head -3",
    f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --status 2>&1",
    f"echo '{PW}' | sudo -S getent passwd 'test-ldap@ldap.justplay.local' 2>&1",
    f"echo '{PW}' | sudo -S ldapsearch -x -H ldap://127.0.0.1 -b 'dc=ldap,dc=justplay,dc=local' '(uid=test-ldap)' uid cn 2>&1 | head -10",
]
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=120)
    out = (o.read() + e.read()).decode(errors='replace')
    print('---', cmd.split('sudo -S ')[-1][:70])
    print(out[:600].strip())
c.close()

print('\n=== DSM login tests ===')
for acct in ['test-ldap@ldap.justplay.local', 'test-ldap']:
    r = dsm_login(acct, 'TestLdap@123')
    print(acct, '->', 'OK' if r.get('success') else r.get('error'))
