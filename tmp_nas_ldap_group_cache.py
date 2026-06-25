#!/usr/bin/env python3
import paramiko
HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo(cmd, timeout=300):
    full = f"echo '{PW}' | sudo -S bash -c {repr(cmd)} 2>&1"
    _, o, e = c.exec_command(full, timeout=timeout)
    return (o.read() + e.read()).decode(errors='replace')

print('=== ldap_group BEFORE ===')
print(sudo('cat /usr/syno/etc/private/ldap_group'))
print('=== fetch all ===')
print(sudo('/usr/syno/bin/synoldapclient --fetch all')[:500])
print('=== ldap_group AFTER ===')
print(sudo('cat /usr/syno/etc/private/ldap_group'))
print('=== SX line ===')
print(sudo('grep -i "^SX" /usr/syno/etc/private/ldap_group || grep -i SX /usr/syno/etc/private/ldap_group'))
print('=== test-ldap1 in groups ===')
print(sudo('grep -i test-ldap1 /usr/syno/etc/private/ldap_group /usr/syno/etc/private/ldap_user'))
print('=== ldapsearch user gidNumber ===')
print(sudo("ldapsearch -x -H ldap://127.0.0.1 -b 'uid=test-ldap1,cn=users,dc=ldap,dc=justplay,dc=local' -D 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local' -w '123123sS@@' gidNumber cn 2>/dev/null"))
print('=== ldapsearch SX gidNumber ===')
print(sudo("ldapsearch -x -H ldap://127.0.0.1 -b 'cn=SX,cn=groups,dc=ldap,dc=justplay,dc=local' -D 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local' -w '123123sS@@' gidNumber memberUid 2>/dev/null | grep -E 'gidNumber|test-ldap'"))
c.close()
