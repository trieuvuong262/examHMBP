#!/usr/bin/env python3
import paramiko
HOST, USER, PW = '100.93.5.42', 'admin', '123123sS@@'
cmds = [
    'ls -la /var/packages/DirectoryServer/',
    'cat /var/packages/DirectoryServer/enabled 2>/dev/null; cat /var/packages/DirectoryServer/INFO 2>/dev/null | head -20',
    'ls /usr/syno/sbin/synopkg /usr/syno/bin/synopkg 2>/dev/null; /usr/syno/sbin/synopkg version 2>/dev/null',
    '/usr/syno/sbin/synopkg status DirectoryServer 2>/dev/null',
    '/usr/syno/sbin/synopkg start DirectoryServer 2>/dev/null',
    'sleep 2; /usr/syno/sbin/synopkg status DirectoryServer 2>/dev/null',
    'ls /var/packages/DirectoryServer/target/ui 2>/dev/null | head -5',
    'find /var/packages/DirectoryServer -name "*.conf" 2>/dev/null | head -10',
]
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, USER, PW, timeout=15, allow_agent=False, look_for_keys=False)
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=60)
    out = (o.read() + e.read()).decode('utf-8', errors='replace').strip()
    print('===', cmd, '===')
    print(out[:2000])
    print()
c.close()
