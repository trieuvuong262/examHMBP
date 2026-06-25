#!/usr/bin/env python3
import ldap
HOST = '100.93.5.42'
BIND = 'uid=root,cn=users,dc=ldap,dc=justplay,dc=local'
PW = '123123sS@@'
BASE = 'dc=ldap,dc=justplay,dc=local'

for port, use_tls in [(389, False), (389, True), (636, False)]:
    try:
        uri = f'ldap://{HOST}:{port}'
        c = ldap.initialize(uri)
        c.set_option(ldap.OPT_REFERRALS, ldap.OPT_OFF)
        if use_tls:
            c.start_tls_s()
        c.simple_bind_s(BIND, PW)
        filt = '(uid=synctest01)'
        res = c.search_s(BASE, ldap.SCOPE_SUBTREE, filt, ['uid'])
        c.unbind_s()
        print(f'OK port={port} tls={use_tls} results={len(res)}')
    except Exception as e:
        print(f'FAIL port={port} tls={use_tls}: {e}')

# test user auth like Odoo
login = 'DNhu'
user_pw = 'justplay@123'
try:
    c = ldap.initialize(f'ldap://{HOST}:389')
    c.set_option(ldap.OPT_REFERRALS, ldap.OPT_OFF)
    c.simple_bind_s(BIND, PW)
    res = c.search_s(BASE, ldap.SCOPE_SUBTREE, f'(uid={login})', ['cn'])
    c.unbind_s()
    if res:
        dn = res[0][0]
        c2 = ldap.initialize(f'ldap://{HOST}:389')
        c2.simple_bind_s(dn, user_pw)
        c2.unbind_s()
        print(f'User auth OK: {login}')
    else:
        print(f'User not found: {login}')
except Exception as e:
    print(f'User auth FAIL: {e}')
