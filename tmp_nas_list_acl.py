#!/usr/bin/env python3
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

cmds = [
    '/usr/syno/sbin/synoshare --list_acl 07_SAN_XUAT',
    '/usr/syno/sbin/synoshare --list_acl docker',
    '/usr/syno/bin/synoacltool -get /volume1/07_SAN_XUAT',
    '/usr/syno/bin/synoacltool -get /volume1/docker',
    '/usr/syno/bin/synoacltool -get /volume1/05_MARKETING',
    '/usr/syno/sbin/synoshare --getmap 07_SAN_XUAT',
]
for cmd in cmds:
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S {cmd} 2>&1", timeout=120)
    out = (o.read()+e.read()).decode(errors='replace')
    print(f'=== {cmd} ===')
    print(out[:4000])
    print()

c.close()
