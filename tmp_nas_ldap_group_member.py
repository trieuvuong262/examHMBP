#!/usr/bin/env python3
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo(cmd):
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S bash -c {repr(cmd)} 2>&1", timeout=120)
    return (o.read()+e.read()).decode(errors='replace')

cmds = [
    '/usr/syno/sbin/synogroup --help 2>&1 | head -25',
    '/usr/syno/sbin/synogroup --enum ALL 2>&1',
    '/usr/syno/sbin/synogroup --get SX 2>&1',
    '/usr/syno/sbin/synogroup --member SX 2>&1 | head -30',
    '/usr/syno/sbin/synogroup --member SX 2>&1 | grep -i test-ldap',
    '/usr/syno/bin/synoldapclient --help 2>&1 | head -40',
    '/usr/syno/bin/synoldapclient --get-groups test-ldap1 2>&1',
    '/usr/syno/bin/synoldapclient --get-user test-ldap1 2>&1',
    'grep -i test-ldap1 /usr/syno/etc/private/ldap_* 2>/dev/null',
    'wc -l /usr/syno/etc/private/ldap_* 2>/dev/null',
    'head -5 /usr/syno/etc/private/ldap_group_member 2>/dev/null',
    'grep -i "test-ldap1\\|SX" /usr/syno/etc/private/ldap_group_member 2>/dev/null | head -20',
    'ls -la /usr/syno/etc/private/ldap* 2>/dev/null',
    'strings /usr/syno/etc/ldapclient/synoldapmeta 2>/dev/null | grep -i test-ldap1 | head',
]
for cmd in cmds:
    print('###', cmd[:75])
    print(sudo(cmd)[:2500])
    print()

c.close()
