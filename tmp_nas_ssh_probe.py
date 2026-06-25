#!/usr/bin/env python3
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('100.93.5.42', username='admin', password='123123sS@@', timeout=15)
cmds = [
    'ls /usr/syno/etc | grep -i ldap',
    'find /usr/syno/etc -maxdepth 3 -iname "*ldap*" 2>/dev/null',
    'find /var/packages/DirectoryServer -name "*.conf" 2>/dev/null | head -15',
    'grep -r "client_enable" /var/packages/DirectoryServer/target 2>/dev/null | head -20',
    'strings /var/packages/DirectoryServer/target/usr/lib/*/SYNO.DirectoryServer.so 2>/dev/null | grep -i client | head -20',
    'cat /var/packages/DirectoryServer/etc/* 2>/dev/null',
]
for cmd in cmds:
    _, o, e = c.exec_command(cmd)
    print('###', cmd)
    print(o.read().decode(errors='replace')[:2000])
    err = e.read().decode(errors='replace')
    if err.strip():
        print('ERR', err[:300])
c.close()
