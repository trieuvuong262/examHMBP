#!/usr/bin/env python3
import paramiko, time

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def run(cmd, t=300):
    print('>>>', cmd)
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S {cmd} 2>&1", timeout=t)
    out = (o.read()+e.read()).decode(errors='replace')
    print(out[:3500])
    print('---')
    return out

# 1) refresh LDAP groups
run('/usr/syno/bin/synoldapclient --fetch all')
time.sleep(3)
run('/usr/syno/sbin/synogroup --rebuild ldap Force1')
time.sleep(2)
run('/usr/syno/sbin/synogroup --get "SX@ldap.justplay.local"')
run('/usr/syno/sbin/synogroup --member "SX@ldap.justplay.local" 2>&1 | grep -i test-ldap | head')

# 2) try add LDAP SX group to share ACL (keep local SX too)
for acl_group in [
    'SX@ldap.justplay.local',
    '@SX@ldap.justplay.local',
]:
    run(f'/usr/syno/sbin/synoshare --setuser 07_SAN_XUAT RW + {acl_group}')

run('/usr/syno/sbin/synoshare --list_acl 07_SAN_XUAT')
run('/usr/syno/bin/synoacltool -get /volume1/07_SAN_XUAT')

c.close()
