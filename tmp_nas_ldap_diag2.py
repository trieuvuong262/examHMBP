#!/usr/bin/env python3
import paramiko
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
cmds = [
    "grep -i ldap /etc/synoinfo.conf",
    "grep -i ldap /etc/passwd /etc/group 2>/dev/null | head",
    "find /usr/syno/etc -name '*ldap*' -type f 2>/dev/null",
    "ls -la /usr/syno/etc/ldapclient/",
    "find /var -path '*ldap*' -type f 2>/dev/null | head -30",
    "cat /var/packages/DirectoryServer/target/etc/data/slapd.d/cn=config/olcDatabase=* 2>/dev/null | head -5",
    "echo '***' | sudo -S ls /var/lib/ldap 2>/dev/null",
    "echo '***' | sudo -S /usr/syno/sbin/synoservicectl --status synoldapclientd 2>&1",
    "echo '***' | sudo -S ps aux | grep ldapclient",
]
for cmd in cmds:
    real = cmd.replace('***', PW)
    _, o, e = c.exec_command(real, timeout=60)
    print('###', cmd[:70])
    print((o.read()+e.read()).decode(errors='replace')[:2500])
    print('---')
c.close()
