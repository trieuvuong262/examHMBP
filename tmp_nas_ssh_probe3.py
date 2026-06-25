#!/usr/bin/env python3
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('100.93.5.42', username='admin', password='123123sS@@', timeout=15)
cmds = [
    'grep -r "enable_client" /usr/syno/synoman/webman/modules/ 2>/dev/null | head -10',
    'find /usr/syno -name "*ldap*client*" 2>/dev/null | head -25',
    'find /usr/syno/etc -name "*.db" 2>/dev/null | head -10',
    'sqlite3 /usr/syno/etc/ldapserver.db ".tables" 2>/dev/null',
    'find / -name "ldapserver.db" 2>/dev/null | head -5',
    'find /volume1/@appdata/DirectoryServer -type f 2>/dev/null | head -30',
]
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=30)
    print('###', cmd)
    print(o.read().decode(errors='replace')[:2500] or '(empty)')
c.close()
