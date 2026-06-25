#!/usr/bin/env python3
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)
_, o, e = c.exec_command(
    f"echo '{PW}' | sudo -S /usr/syno/bin/synoldapclient --fetch all 2>&1",
    timeout=300,
)
out = (o.read() + e.read()).decode(errors='replace')
print(out[:800])
_, o2, _ = c.exec_command(
    f"echo '{PW}' | sudo -S grep -i test-ldap1 /usr/syno/etc/private/ldap_user 2>&1",
    timeout=60,
)
print('cache:', (o2.read()).decode(errors='replace').strip())
c.close()
