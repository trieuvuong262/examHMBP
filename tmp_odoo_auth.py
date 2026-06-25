import xmlrpc.client as x
c = x.ServerProxy('http://127.0.0.1:8069/xmlrpc/2/common', allow_none=True)
print('Odoo uid:', c.authenticate('justplay_pilot', 'test-ldap', 'TestLdap@123', {}))
