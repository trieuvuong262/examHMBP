#!/usr/bin/env python3
import paramiko
HOST, USER, PW = '100.93.5.42', 'admin', '123123sS@@'
cmds = [
    'which synopkg; synopkg --help 2>&1 | head -20',
    'ls /var/packages/ 2>/dev/null | grep -iE "ldap|directory"',
    'synopkg list 2>/dev/null | grep -iE "ldap|directory" || true',
    'ls /usr/syno/etc/packages/ 2>/dev/null | grep -iE "ldap|directory" || true',
    'cat /etc/synoinfo.conf 2>/dev/null | grep -i ldap || true',
]
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, USER, PW, timeout=15, allow_agent=False, look_for_keys=False)
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=30)
    out = (o.read() + e.read()).decode('utf-8', errors='replace').strip()
    print('===', cmd[:60], '===')
    print(out[:1500])
    print()
c.close()
