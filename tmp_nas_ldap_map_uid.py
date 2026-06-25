#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
import paramiko, time
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo(cmd):
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S {cmd}", timeout=180)
    out = (o.read()+e.read()).decode(errors='replace')
    print('>>>', cmd)
    print(out[:1500])
    return out

sudo('/usr/syno/bin/synoldapclient --map-uid 1000 99999999')
sudo('/usr/syno/bin/synoldapclient --map-gid 1000 99999999')
sudo('/usr/syno/bin/synoldapclient --fetch all')
sudo('/usr/syno/bin/synoldapclient --get-user test-ldap')
sudo('/usr/syno/bin/synoldapclient --status')
c.close()

for account, pwd in [
    ('test-ldap', 'TestLdap@123'),
    ('test-ldap@ldap.justplay.local', 'TestLdap@123'),
    ('uid=test-ldap,cn=users,dc=ldap,dc=justplay,dc=local', 'TestLdap@123'),
]:
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':account,'passwd':pwd,'session':'t','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    print('DSM login', account[:40], '->', 'OK' if p.get('success') else p.get('error'))
