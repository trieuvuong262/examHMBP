#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request

HOST, PW = '100.93.5.42', 'TestLdap@123'
CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'

def login(account):
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': account, 'passwd': PW, 'format': 'sid', 'enable_syno_token': 'yes',
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'),
        context=CTX, timeout=20,
    ) as r:
        return json.loads(r.read().decode())

import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username='admin', password='123123sS@@', timeout=15)
_, o, _ = c.exec_command(
    "echo '123123sS@@' | sudo -S ldapsearch -x -H ldap://127.0.0.1 "
    "-b 'dc=ldap,dc=justplay,dc=local' '(uid=test-ldap1)' uid cn dn 2>/dev/null",
    timeout=60,
)
print('=== LDAP (1 entry only) ===')
print((o.read()).decode(errors='replace')[:600])
_, o, _ = c.exec_command(
    "echo '123123sS@@' | sudo -S grep test-ldap1 /usr/syno/etc/private/ldap_user",
    timeout=60,
)
print('=== NAS cache line ===')
print((o.read()).decode(errors='replace').strip())
c.close()

for acct in ['test-ldap1', 'test-ldap1@ldap.justplay.local']:
    r = login(acct)
    if r.get('success'):
        print(f'DSM login {acct!r} -> OK, sid={r["data"]["sid"][:12]}...')
    else:
        print(f'DSM login {acct!r} ->', r.get('error'))
