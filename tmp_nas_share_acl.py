#!/usr/bin/env python3
import paramiko, json, ssl, urllib.parse, urllib.request

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo(cmd, t=120):
    full = f"echo '{PW}' | sudo -S bash -c {repr(cmd)} 2>&1"
    _, o, e = c.exec_command(full, timeout=t)
    return (o.read() + e.read()).decode(errors='replace')

cmds = [
    'which synoshare synoacltool synowebapi 2>/dev/null; ls /usr/syno/bin/syno*share* 2>/dev/null | head',
    'synoshare --help 2>&1 | head -40',
    'synoshare --get 07_SAN_XUAT permission 2>&1',
    'synoshare --get 07_SAN_XUAT 2>&1',
    'cat /usr/syno/etc/share/07_SAN_XUAT.conf 2>/dev/null',
    'ls /usr/syno/etc/share/ 2>/dev/null | head -20',
    'grep -r "07_SAN_XUAT" /usr/syno/etc/share/ 2>/dev/null | head -20',
    'find /usr/syno/etc -name "*07_SAN*" 2>/dev/null',
    'synoacltool -get /volume1/07_SAN_XUAT 2>&1 | head -40',
]
for cmd in cmds:
    print('###', cmd[:70])
    print(sudo(cmd)[:2000])
    print()

# DSM API share permission via admin
CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'
data = urllib.parse.urlencode({
    'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
    'account': ADMIN, 'passwd': PW, 'session': 'share', 'format': 'sid', 'enable_syno_token': 'yes',
}).encode()
with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
    p = json.loads(r.read().decode())
sid, token = p['data']['sid'], p['data'].get('synotoken', '')

for api, ver, method, extra in [
    ('SYNO.Core.Share.Permission', '1', 'get', {'name': '07_SAN_XUAT'}),
    ('SYNO.Core.Share.Permission', '1', 'load', {'name': '07_SAN_XUAT'}),
    ('SYNO.Core.Share.Permission', '2', 'get', {'name': '07_SAN_XUAT'}),
    ('SYNO.Core.Share', '1', 'get', {'name': '07_SAN_XUAT'}),
]:
    q = {'_sid': sid, 'api': api, 'version': ver, 'method': method, **extra}
    if token:
        q['SynoToken'] = token
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=urllib.parse.urlencode(q).encode(), method='POST')
    if token:
        req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        res = json.loads(r.read().decode())
    print(f'API {api} v{ver} {method}:', json.dumps(res, ensure_ascii=False)[:1500])

c.close()
