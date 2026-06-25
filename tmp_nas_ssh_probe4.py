#!/usr/bin/env python3
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('100.93.5.42', username='admin', password='123123sS@@', timeout=15)
cmds = [
    '/usr/syno/bin/synoldapclient --help 2>&1',
    '/usr/syno/bin/synoldapclient 2>&1 | head -30',
    'ls -la /usr/syno/bin/synoldapclient*',
    'strings /usr/syno/bin/synoldapclient 2>/dev/null | head -40',
    'grep -r "synoldapclient" /usr/syno/synoman/webman/modules/DirectoryService/ 2>/dev/null | head -15',
    'ls /usr/syno/synoman/webman/modules/ | grep -i dir',
]
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=30)
    print('###', cmd)
    print((o.read() + e.read()).decode(errors='replace')[:3000] or '(empty)')
c.close()
