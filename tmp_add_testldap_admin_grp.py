#!/usr/bin/env python3
import ssl
from ldap3 import MODIFY_ADD, Server, Connection, Tls

HOST, PW = '100.93.5.42', '123123sS@@'
BASE = 'dc=ldap,dc=justplay,dc=local'
ROOT = f'uid=root,cn=users,{BASE}'
tls = Tls(validate=ssl.CERT_NONE)
c = Connection(Server(HOST, 636, use_ssl=True, tls=tls), user=ROOT, password=PW, auto_bind=True)
for grp in ['administrators', 'Directory Operators']:
    dn = f'cn={grp},cn=groups,{BASE}'
    c.modify(dn, {'memberUid': [(MODIFY_ADD, ['test-ldap'])]})
    print(grp, c.result)
c.unbind()
