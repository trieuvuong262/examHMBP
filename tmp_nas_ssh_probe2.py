#!/usr/bin/env python3
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('100.93.5.42', username='admin', password='123123sS@@', timeout=15)
cmds = [
    'ls -la /usr/syno/etc/ldapclient/',
    'cat /usr/syno/etc/ldapclient/* 2>/dev/null',
    'cat /usr/syno/etc/user.data.conf/ldap_client.config 2>/dev/null',
    'cat /usr/syno/etc/openldap/ldap.conf 2>/dev/null',
    'ls -la /var/packages/DirectoryServer/var/ 2>/dev/null',
    'find /var/packages/DirectoryServer -name "*.json" 2>/dev/null | head -20',
    'find /volume1/@appconf/DirectoryServer -type f 2>/dev/null | head -20',
    'cat /volume1/@appconf/DirectoryServer/* 2>/dev/null | head -80',
]
for cmd in cmds:
    _, o, e = c.exec_command(cmd)
    print('###', cmd)
    out = o.read().decode(errors='replace')
    print(out[:3000] if out else '(empty)')
c.close()
