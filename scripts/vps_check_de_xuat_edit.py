import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from hrm.module_permissions import MODULE_DE_XUAT, user_can_access_module, user_can_edit_module

User = get_user_model()
for u in User.objects.filter(is_active=True, profile__is_employed=True).select_related('profile').order_by('username'):
    if user_can_edit_module(u, MODULE_DE_XUAT):
        dept = u.profile.department.name if u.profile.department_id else '-'
        print(f'{u.username:14} {u.profile.full_name:25} | {dept}')
