#!/usr/bin/env python3
import paramiko
import time

HOST = '100.93.5.42'
ADMIN, PW = 'admin', '123123sS@@'
LDAP_HOST = 'ldap.justplay.local'
BASE_DN = 'dc=ldap,dc=justplay,dc=local'
BIND_DN = 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local'
BIND_PW = '123123sS@@'
TEST_USER, TEST_PW = 'test-ldap', 'TestLdap@123'

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def run(cmd, timeout=120):
    print('>>>', cmd)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors='replace')
    err = e.read().decode(errors='replace')
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[:4000])
    if err.strip():
        print('STDERR:', err[:2000])
    print('exit', code)
    print('---')
    return code, out, err

run('/usr/syno/bin/synoldapclient --status')
# try bind - may need sudo
for host in ['127.0.0.1', 'ldap.justplay.local', HOST]:
    code, out, err = run(
        f'/usr/syno/bin/synoldapclient --bind no {host} {BASE_DN} {BIND_DN} {BIND_PW}'
    )
    if code == 0:
        break

time.sleep(3)
run('/usr/syno/bin/synoldapclient --status')
run('/usr/syno/bin/synoldapclient --fetch all')
run(f'/usr/syno/bin/synoldapclient --get-user {TEST_USER}')
run('/usr/syno/bin/synoldapclient --support-cifs pam')

# DSM login test via curl on NAS itself
run(
    "curl -sk -X POST 'https://127.0.0.1:5001/webapi/auth.cgi' "
    "-d 'api=SYNO.API.Auth&version=7&method=login&account=test-ldap&passwd=TestLdap@123&session=t&format=sid'"
)

c.close()
