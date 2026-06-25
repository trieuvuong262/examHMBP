#!/usr/bin/env python3
import paramiko
HOST, USER, PW = '100.93.5.42', 'admin', '123123sS@@'
cmds = [
    'grep -r "SYNO.DirectoryServer.Server" /volume1/@appstore/DirectoryServer/webapi/ 2>/dev/null | head -20',
    'find /volume1/@appstore/DirectoryServer/webapi -name "*.json" 2>/dev/null | head -20',
    'cat /volume1/@appstore/DirectoryServer/webapi/SYNO.DirectoryServer.Server.json 2>/dev/null',
    'ls /volume1/@appstore/DirectoryServer/webapi/',
    'sudo -n /usr/syno/bin/synopkg start DirectoryServer 2>&1',
    'sudo -n /usr/syno/bin/synopkg status DirectoryServer 2>&1',
    'id; groups',
]
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, USER, PW, timeout=15, allow_agent=False, look_for_keys=False)
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=90)
    out = (o.read() + e.read()).decode('utf-8', errors='replace').strip()
    print('===', cmd[:75], '===')
    print(out[:4000])
    print()
c.close()
