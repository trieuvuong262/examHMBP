#!/usr/bin/env python3
import paramiko, json, ssl, urllib.parse, urllib.request

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo(cmd):
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S bash -c {repr(cmd)} 2>&1", timeout=120)
    return (o.read()+e.read()).decode(errors='replace')

searches = [
    'find /usr/syno/etc -type f 2>/dev/null | xargs grep -l "07_SAN_XUAT" 2>/dev/null | head -20',
    'find /etc -type f 2>/dev/null | xargs grep -l "07_SAN_XUAT" 2>/dev/null | head -20',
    'ls -la /usr/syno/etc/privilege* 2>/dev/null; ls -la /usr/syno/etc/smb* 2>/dev/null | head',
    'cat /usr/syno/etc/privilege.conf 2>/dev/null | head -5',
    'grep -r "SX" /usr/syno/etc/privilege* 2>/dev/null | head -20',
    'ls /usr/syno/sbin/ | grep -i share',
    'ls /usr/syno/bin/ | grep -iE "share|priv|acl"',
]
for cmd in searches:
    print('###', cmd[:65])
    print(sudo(cmd)[:2500])
    print()

c.close()

CTX = ssl._create_unverified_context()
BASE = f'https://{HOST}:5556'
data = urllib.parse.urlencode({
    'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
    'account': ADMIN, 'passwd': PW, 'session': 'FileStation', 'format': 'sid', 'enable_syno_token': 'yes',
}).encode()
with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
    p = json.loads(r.read().decode())
print('admin FileStation login:', p.get('success'), p.get('error'))
if p.get('success'):
    sid, token = p['data']['sid'], p['data'].get('synotoken', '')
    for method, extra in [
        ('list', {}),
        ('get', {'name': '07_SAN_XUAT'}),
        ('load', {'name': '07_SAN_XUAT'}),
        ('enum', {}),
    ]:
        q = {'_sid': sid, 'SynoToken': token, 'api': 'SYNO.Core.Share.Permission', 'version': '1', 'method': method, **extra}
        req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=urllib.parse.urlencode(q).encode(), method='POST')
        req.add_header('X-SYNO-TOKEN', token)
        with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
            res = json.loads(r.read().decode())
        print('Permission', method, extra, '->', json.dumps(res, ensure_ascii=False)[:1500])

    q = {'_sid': sid, 'SynoToken': token, 'api': 'SYNO.Core.Share.PermissionReport', 'version': '1', 'method': 'list', 'name': '07_SAN_XUAT'}
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=urllib.parse.urlencode(q).encode(), method='POST')
    req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        res = json.loads(r.read().decode())
    print('PermissionReport:', json.dumps(res, ensure_ascii=False)[:2000])
