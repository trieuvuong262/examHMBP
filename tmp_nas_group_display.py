#!/usr/bin/env python3
import json
import ssl
import urllib.parse
import urllib.request
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'

def dsm_login(account, passwd):
    data = urllib.parse.urlencode({
        'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
        'account': account, 'passwd': passwd, 'format': 'sid', 'enable_syno_token': 'yes',
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'),
        context=CTX, timeout=20,
    ) as r:
        return json.loads(r.read().decode())

def api(sid, token, api, method, version='1', **p):
    q = {'_sid': sid, 'api': api, 'version': version, 'method': method, **p}
    if token:
        q['SynoToken'] = token
    data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    if token:
        req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        return json.loads(r.read().decode())

for acct in ['test-ldap1@ldap.justplay.local', 'admin']:
    r = dsm_login(acct, 'TestLdap@123' if 'test-ldap' in acct else PW)
    print('=== login', acct, '->', 'OK' if r.get('success') else r.get('error'))
    if not r.get('success'):
        continue
    sid, token = r['data']['sid'], r['data'].get('synotoken', '')
    for api_name, method, ver in [
        ('SYNO.Core.User', 'get', '1'),
        ('SYNO.Core.Group', 'list', '1'),
        ('SYNO.Core.Directory.LDAP', 'get', '2'),
    ]:
        try:
            res = api(sid, token, api_name, method, version=ver)
            print(api_name, json.dumps(res, ensure_ascii=False)[:600])
        except Exception as e:
            print(api_name, 'ERR', e)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
cmds = [
    '/usr/syno/bin/synoldapclient --get-user test-ldap1',
    '/usr/syno/bin/synoldapclient --get-user test-ldap',
    'grep -i test-ldap1 /usr/syno/etc/private/ldap_group 2>/dev/null | head -5',
    'wc -l /usr/syno/etc/private/ldap_group 2>/dev/null',
    'grep -i ",SX," /usr/syno/etc/private/ldap_group 2>/dev/null | head -3',
    'grep -i "test-ldap1" /usr/syno/etc/private/ldap_group 2>/dev/null | head -5',
]
for cmd in cmds:
    full = f"echo '{PW}' | sudo -S {cmd} 2>&1"
    _, o, e = c.exec_command(full, timeout=120)
    out = (o.read() + e.read()).decode(errors='replace')
    print('---', cmd)
    print(out[:1000].strip())
c.close()
