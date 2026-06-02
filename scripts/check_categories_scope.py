import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from equipment.models import DeviceCategory
from equipment.scope import SCOPE_IT, SCOPE_PRODUCTION
from equipment.services.scope_ui import categories_by_group_for_scope

print('active_total', DeviceCategory.objects.filter(is_active=True).count())
print('it_profile', DeviceCategory.objects.filter(is_active=True, import_profile='it').count())
print('machine_profile', DeviceCategory.objects.filter(is_active=True, import_profile='machine').count())
for scope in (SCOPE_IT, SCOPE_PRODUCTION):
    groups = categories_by_group_for_scope(scope)
    n = sum(len(items) for _g, _l, items in groups)
    print(scope, 'groups', len(groups), 'items', n)
