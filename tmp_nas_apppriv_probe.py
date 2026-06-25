#!/usr/bin/env python3
import paramiko
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
cmds = [
    "ls /usr/syno/bin/synoapp* 2>/dev/null; ls /usr/syno/sbin/synoapp* 2>/dev/null",
    "ls /usr/syno/bin/synouser* 2>/dev/null",
    "synouser --help 2>&1 | head -30",
    "synogroup --help 2>&1 | head -30",
    "ls /usr/syno/etc/apppriv* 2>/dev/null; ls /usr/syno/etc/appportal* 2>/dev/null",
    "grep -r DSM /usr/syno/etc/apppriv 2>/dev/null | head -5",
]
for cmd in cmds:
    full = f"echo '{PW}' | sudo -S bash -c \"{cmd}\" 2>&1"
    _, o, e = c.exec_command(full, timeout=60)
    out = (o.read()+e.read()).decode(errors='replace')
    print('###', cmd[:70])
    print(out[:1200])
c.close()
