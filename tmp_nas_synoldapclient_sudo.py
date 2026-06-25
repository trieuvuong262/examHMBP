#!/usr/bin/env python3
import paramiko
import time

HOST = '100.93.5.42'
ADMIN, PW = 'admin', '123123sS@@'
BASE_DN = 'dc=ldap,dc=justplay,dc=local'
BIND_DN = 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local'

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def run(cmd, timeout=120):
    print('>>>', cmd.replace(PW, '***'))
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors='replace')
    err = e.read().decode(errors='replace')
    code = o.channel.recv_exit_status()
    print(out[:4000] if out.strip() else '(no stdout)')
    if err.strip():
        print('STDERR:', err[:2500])
    print('exit', code, '\n---')
    return code

# sudo bind attempts
run(f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --status")
for host in ['127.0.0.1', 'ldap.justplay.local']:
    code = run(
        f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --bind no {host} {BASE_DN} {BIND_DN} {PW}"
    )
    if code == 0:
        break

time.sleep(5)
run(f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --status")
run(f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --get-user test-ldap")
run(f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --support-cifs pam")

c.close()
