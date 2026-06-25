#!/usr/bin/env python3
import paramiko

HOST, ADMIN, PW = '100.93.5.42', 'admin', '123123sS@@'
DOMAIN = 'ldap.justplay.local'
# share -> local group in ACL (from naming convention)
DEPT_SHARES = {
    '02_HANH_CHINH_NHAN_SU': 'HCNS',
    '03_TAI_CHINH_KE_TOAN': 'TCKT',
    '05_MARKETING': 'MKT',
    '06_RnD_THIET_KE_SAN_PHAM': 'RnD',
    '07_SAN_XUAT': 'SX',
    '10_HE_THONG_CNTT': 'IT',
    '01_BAN_GIAM_DOC': 'TGD',
}

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=ADMIN, password=PW, timeout=15)

def sudo(cmd):
    _, o, e = c.exec_command(f"echo '{PW}' | sudo -S {cmd} 2>&1", timeout=120)
    return (o.read()+e.read()).decode(errors='replace')

for share, grp in DEPT_SHARES.items():
    acl = sudo(f'/usr/syno/sbin/synoshare --list_acl {share}')
    ldap_grp = f'@{grp}@{DOMAIN}'
    has_ldap = ldap_grp in acl
    has_local = f'@{grp}' in acl and ldap_grp not in acl
    print(f'{share}: local@{grp}={("@%s" % grp) in acl} ldap={has_ldap}')
    if has_local and not has_ldap:
        out = sudo(f'/usr/syno/sbin/synoshare --setuser {share} RW + {ldap_grp}')
        if ldap_grp in out:
            print('  -> ADDED', ldap_grp)
        else:
            print('  -> add may have failed')

c.close()
