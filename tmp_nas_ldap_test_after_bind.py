#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
import paramiko
import time

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()
TEST_USER, TEST_PW = 'test-ldap', 'TestLdap@123'

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo(cmd):
    print('>>>', cmd.replace(PW, '***'))
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S {cmd}", timeout=300)
    out = o.read().decode(errors='replace')
    err = e.read().decode(errors='replace')
    print(out[:3000] if out.strip() else '(no stdout)')
    if err.strip():
        print('ERR:', err[:1500])
    print('---')

sudo('/usr/syno/bin/synoldapclient --fetch all')
sudo('/usr/syno/bin/synoldapclient --get-user test-ldap')
sudo('/usr/syno/bin/synoldapclient --status')

c.close()

# DSM API checks
def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'x','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        return json.loads(r.read().decode())['data']['sid']

def get(sid, api, method):
    q = urllib.parse.urlencode({'_sid':sid,'api':api,'version':'1','method':method})
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/entry.cgi?{q}'), context=CTX, timeout=30) as r:
        return json.loads(r.read().decode())

sid = login()
print('LDAP API:', json.dumps(get(sid,'SYNO.Core.Directory.LDAP','get'), ensure_ascii=False)[:1000])
print('DS Server:', json.dumps(get(sid,'SYNO.DirectoryServer.Server','get').get('data',{}), ensure_ascii=False)[:600])

for user, pwd in [(TEST_USER, TEST_PW), ('admin', PW)]:
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':user,'passwd':pwd,'session':'t','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    print(f'DSM login {user}:', 'OK' if p.get('success') else p.get('error'))

# Odoo
import xmlrpc.client
uid = xmlrpc.client.ServerProxy('http://103.90.224.203:8069/xmlrpc/2/common', allow_none=True)
# can't reach 8069 from portal - skip or use odoo container via ssh
