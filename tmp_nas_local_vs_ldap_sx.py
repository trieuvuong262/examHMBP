#!/usr/bin/env python3
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo(cmd):
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S bash -c {repr(cmd)} 2>&1", timeout=180)
    return (o.read()+e.read()).decode(errors='replace')

cmds = [
    '/usr/syno/sbin/synogroup --enum ldap 2>&1',
    '/usr/syno/sbin/synogroup --enum all 2>&1 | head -40',
    '/usr/syno/sbin/synogroup --get "SX@ldap.justplay.local" 2>&1',
    '/usr/syno/bin/synoldapclient --get-group SX 2>&1',
    '/usr/syno/sbin/synogroup --get SX 2>&1 | head -20',
    'grep SX /usr/syno/etc/private/ldap_group',
    '/usr/syno/sbin/synoshare --list_acl 07_SAN_XUAT',
    # compare DNhu local vs ldap
    '/usr/syno/sbin/synouser --get DNhu 2>&1 | head -15',
]
for cmd in cmds:
    print('###', cmd[:75])
    print(sudo(cmd)[:3000])
    print()

c.close()
