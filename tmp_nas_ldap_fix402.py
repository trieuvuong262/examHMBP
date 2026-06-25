#!/usr/bin/env python3
import json, ssl, urllib.parse, urllib.request
import paramiko, time
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
BASE = f'https://{HOST}:5556'
CTX = ssl._create_unverified_context()

def login():
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':ADMIN,'passwd':PW,'session':'Core','format':'sid','enable_syno_token':'yes'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    return p['data']['sid'], p['data'].get('synotoken','')

def post(sid, token, **params):
    q = {'_sid': sid, **params}
    if token: q['SynoToken'] = token
    data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(f'{BASE}/webapi/entry.cgi', data=data, method='POST')
    if token: req.add_header('X-SYNO-TOKEN', token)
    with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
        return json.loads(r.read().decode())

sid, token = login()
for fields in [
    {'enable_idmap':'true'},
    {'enable_client':'true','enable_idmap':'true'},
]:
    r = post(sid, token, api='SYNO.Core.Directory.LDAP', version='2', method='set', **fields)
    print('LDAP.set', fields, json.dumps(r, ensure_ascii=False)[:400])

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
for cmd in [
    f"echo '{PW}' | sudo -S synosystemctl restart synoldapclientd",
    f"echo '{PW}' | sudo -S /usr/syno/sbin/synoldapclientd --status 2>&1",
    f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --fetch all",
    f"echo '{PW}' | sudo -S getent passwd test-ldap",
]:
    _, o, e = c.exec_command(cmd, timeout=120)
    print('###', cmd.split('sudo -S ')[-1][:60])
    print((o.read()+e.read()).decode(errors='replace')[:800])
c.close()

time.sleep(3)
for user, pwd in [('test-ldap','TestLdap@123')]:
    data = urllib.parse.urlencode({'api':'SYNO.API.Auth','version':'7','method':'login','account':user,'passwd':pwd,'session':'t','format':'sid'}).encode()
    with urllib.request.urlopen(urllib.request.Request(f'{BASE}/webapi/auth.cgi', data=data, method='POST'), context=CTX, timeout=20) as r:
        p = json.loads(r.read().decode())
    print('DSM', user, 'OK' if p.get('success') else p.get('error'))
