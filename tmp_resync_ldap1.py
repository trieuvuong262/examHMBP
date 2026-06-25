import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()
from django.contrib.auth.models import User
from audit.services.nas_ldap_sync import nas_ldap_group_for_department, provision_ldap_user
u = User.objects.select_related('profile__department').get(username='test-ldap1')
dept = u.profile.department.name if u.profile.department else None
print('dept', repr(dept), 'group', nas_ldap_group_for_department(dept))
print(provision_ldap_user(u, password='TestLdap@123'))
