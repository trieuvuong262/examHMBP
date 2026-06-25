#!/usr/bin/env python3
"""Tạo user test-ldap1 (SẢN XUẤT) và đồng bộ LDAP + Odoo."""
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import authenticate
from django.contrib.auth.models import User

from audit.services.nas_ldap_sync import nas_ldap_group_for_department, provision_ldap_user
from audit.services.odoo_sync import provision_erp_user, user_has_odoo_portal_access
from hrm.models import Department, PermissionGroup, Profile

USERNAME = 'test-ldap1'
PASSWORD = 'TestLdap@123'
FULL_NAME = 'NV Test LDAP1 SX'
DEPT_NAME = 'SẢN XUẤT'

dept = Department.objects.filter(name=DEPT_NAME, is_active=True).first()
if not dept:
    raise SystemExit(f'Không tìm thấy phòng ban: {DEPT_NAME}')

user, created = User.objects.get_or_create(
    username=USERNAME,
    defaults={
        'email': f'{USERNAME}@justplay.local',
        'first_name': FULL_NAME,
        'is_active': True,
    },
)
user.set_password(PASSWORD)
user.is_active = True
user.email = user.email or f'{USERNAME}@justplay.local'
user.first_name = FULL_NAME
user.save()
print('User:', USERNAME, 'created' if created else 'updated')

profile, _ = Profile.objects.get_or_create(
    user=user,
    defaults={
        'full_name': FULL_NAME,
        'department': dept,
        'is_employed': True,
        'must_change_password': False,
    },
)
profile.full_name = FULL_NAME
profile.department = dept
profile.is_employed = True
profile.must_change_password = False

sx_group = PermissionGroup.objects.filter(slug__icontains='sx').order_by('slug').first()
if sx_group:
    profile.permission_group = sx_group
    print('Permission group:', sx_group.slug)
profile.save()

print('LDAP group:', nas_ldap_group_for_department(dept.name))
print('LDAP sync:', provision_ldap_user(user, password=PASSWORD))
print('Odoo sync:', provision_erp_user(user, password=PASSWORD))
print('Odoo menu access:', user_has_odoo_portal_access(user))
print('Portal auth:', bool(authenticate(username=USERNAME, password=PASSWORD)))
