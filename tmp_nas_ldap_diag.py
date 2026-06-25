#!/usr/bin/env python3
import paramiko
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
cmds = [
    "echo '***' | sudo -S ldapsearch -x -H ldap://127.0.0.1 -b dc=ldap,dc=justplay,dc=local -D 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local' -w '123123sS@@' '(uid=test-ldap)' 2>&1 | head -30",
    "echo '***' | sudo -S ps aux | grep slapd | grep -v grep",
    "echo '***' | sudo -S /usr/syno/bin/synoldapclient --status",
    "echo '***' | sudo -S cat /etc/nsswitch.conf | grep -i ldap",
    "echo '***' | sudo -S ls -la /etc/pam.d/ | grep -i ldap",
    "echo '***' | sudo -S grep -r ldap /etc/pam.d/system-auth 2>/dev/null | head",
]
for cmd in cmds:
    real = cmd.replace('***', PW)
    _, o, e = c.exec_command(real, timeout=60)
    print('###', cmd[:80])
    print((o.read()+e.read()).decode(errors='replace')[:2000])
    print('---')
c.close()
