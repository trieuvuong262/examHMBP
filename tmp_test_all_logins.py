import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()
from django.contrib.auth import authenticate
import xmlrpc.client
print('Portal auth:', bool(authenticate(username='test-ldap', password='TestLdap@123')))
c = xmlrpc.client.ServerProxy('http://odoo-web:8069/xmlrpc/2/common', allow_none=True)
print('Odoo uid:', c.authenticate('justplay_pilot', 'test-ldap', 'TestLdap@123', {}))
