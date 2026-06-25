#!/usr/bin/env python3
import paramiko
HOST, USER, PW = '100.93.5.42', 'admin', '123123sS@@'
cmds = [
    'tail -80 /var/log/synopkg.log 2>/dev/null | grep -i DirectoryServer',
    'tail -50 /var/log/synopkg.log 2>/dev/null',
    'ls -la /volume1/@appdata/DirectoryServer/ 2>/dev/null',
    'find /volume1/@appdata/DirectoryServer -type f 2>/dev/null | head -30',
    'cat /volume1/@appstore/DirectoryServer/conf/* 2>/dev/null | head -50',
    'ls -la /volume1/@appstore/DirectoryServer/ 2>/dev/null | head -20',
    '/usr/syno/bin/synopkg restart DirectoryServer 2>&1',
    'sleep 5; /usr/syno/bin/synopkg status DirectoryServer 2>&1',
    'ls /var/packages/DirectoryServer/scripts/ 2>/dev/null',
    'sh /var/packages/DirectoryServer/scripts/start-stop-status start 2>&1 | head -30',
]
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, USER, PW, timeout=15, allow_agent=False, look_for_keys=False)
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=120)
    out = (o.read() + e.read()).decode('utf-8', errors='replace').strip()
    print('===', cmd[:70], '===')
    print(out[:3000])
    print()
c.close()
