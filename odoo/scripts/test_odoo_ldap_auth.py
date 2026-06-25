#!/usr/bin/env python3
"""Test Odoo login via LDAP after auth_ldap config."""
import xmlrpc.client

URL = 'http://127.0.0.1:8069'
DB = 'justplay_pilot'

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common', allow_none=True)
version = common.version()
print('Odoo', version.get('server_version'))

for login, password in [
    ('DNhu', 'justplay@123'),
    ('admin', '123123sS@@'),
]:
    uid = common.authenticate(DB, login, password, {})
    print(f'auth {login!r}: uid={uid}')
