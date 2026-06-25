#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request, time
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'x','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())['data']['sid']

def post(sid, **p):
    data = urllib.parse.urlencode({'_sid':sid,**p}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST'), context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())

def get(sid, api, method, **extra):
    q = urllib.parse.urlencode({'_sid':sid,'api':api,'version':'1','method':method,**extra})
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi?{q}'), context=CTX, timeout=60) as r:
        return json.loads(r.read().decode())

sid = login()
r = post(sid, api='SYNO.Core.Directory.LDAP.Refresh', version='1', method='set')
print('refresh:', json.dumps(r, ensure_ascii=False)[:400])

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
for cmd in [
    f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --fetch all",
    f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --get-user test-ldap",
    f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --get-user DNhu",
]:
    _, o, e = c.exec_command(cmd, timeout=300)
    print('###', cmd.split('synoldapclient')[1])
    print(o.read().decode()[:500])
    print(e.read().decode()[:500])
c.close()

time.sleep(5)
users = get(sid, 'SYNO.Core.Directory.LDAP.User', 'list', offset=0, limit=20)
print('LDAP users API:', json.dumps(users, ensure_ascii=False)[:1500])

for user, pwd in [('test-ldap','TestLdap@123'),('DNhu','justplay@123')]:
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':user,'passwd':pwd,'session':'t','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    print(f'DSM {user}:', 'OK' if p.get('success') else p.get('error'))
