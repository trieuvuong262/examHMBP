#!/usr/bin/env python3
import paramiko
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
cmds = [
    f"echo '{PW}' | sudo -S wc -l /usr/syno/etc/private/ldap_user /usr/syno/etc/private/ldap_group",
    f"echo '{PW}' | sudo -S grep -i test-ldap /usr/syno/etc/private/ldap_user 2>/dev/null | head -5",
    f"echo '{PW}' | sudo -S grep -i 'test-ldap\\|DNhu' /usr/syno/etc/private/ldap_user 2>/dev/null | head -5",
    f"echo '{PW}' | sudo -S head -3 /usr/syno/etc/private/ldap_user",
    f"echo '{PW}' | sudo -S /usr/syno/bin/synouser --help 2>&1 | head -20",
]
for cmd in cmds:
    _, o, e = c.exec_command(cmd, timeout=60)
    print('###', cmd[30:90])
    print((o.read()+e.read()).decode(errors='replace')[:2000])
c.close()
