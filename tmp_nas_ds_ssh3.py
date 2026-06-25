#!/usr/bin/env python3
import paramiko
HOST, USER, PW = '100.93.5.42', 'admin', '123123sS@@'
SYNOPKG = '/usr/syno/bin/synopkg'
cmds = [
    f'{SYNOPKG} version',
    f'{SYNOPKG} status DirectoryServer',
    f'{SYNOPKG} start DirectoryServer',
    'sleep 3',
    f'{SYNOPKG} status DirectoryServer',
    'ls -la /volume1/@appconf/DirectoryServer/ 2>/dev/null',
    'find /volume1/@appconf/DirectoryServer -type f 2>/dev/null | head -20',
    'cat /volume1/@appconf/DirectoryServer/*.conf 2>/dev/null | head -40',
    'ps aux | grep -iE "slapd|ldap|directory" | grep -v grep',
]
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, USER, PW, timeout=15, allow_agent=False, look_for_keys=False)
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=90)
    out = (o.read() + e.read()).decode('utf-8', errors='replace').strip()
    print('===', cmd, '===')
    print(out[:2500])
    print()
c.close()
