#!/usr/bin/env python3
import paramiko
HOST, USER, PW = '100.93.5.42', 'admin', '123123sS@@'
cmds = [
    'grep -rho "server_enable\\|fqdn\\|bind\\|admin_password\\|ldap_password" /volume1/@appstore/DirectoryServer/ui/ 2>/dev/null | sort -u | head -30',
    'strings /volume1/@appstore/DirectoryServer/webapi/SYNO.DirectoryServer.so 2>/dev/null | grep -iE "server_enable|fqdn|password|set" | head -40',
    'grep -r "server_enable" /volume1/@appstore/DirectoryServer/ui/config/ 2>/dev/null | head -10',
]
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, USER, PW, timeout=15, allow_agent=False, look_for_keys=False)
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=120)
    out = (o.read() + e.read()).decode('utf-8', errors='replace').strip()
    print('===', cmd[:70], '===')
    print(out[:5000])
    print()
c.close()
