#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
import paramiko
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE_URL = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
_, o, e = c.exec_command(f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --fetch all", timeout=300)
print((o.read()+e.read()).decode()[:500])
c.close()

for account, pwd in [
    ('test-ldap@ldap.justplay.local', 'TestLdap@123'),
    ('test-ldap', 'TestLdap@123'),
]:
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':account,'passwd':pwd,'session':'t','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE_URL}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    print('DSM', account, '->', 'OK sid' if p.get('success') else p.get('error'))
