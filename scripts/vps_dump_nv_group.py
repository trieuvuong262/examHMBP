import json
from django.contrib.auth import get_user_model
from hrm.models import PermissionGroup
from hrm.module_permissions import MODULE_REPORTS

User = get_user_model()
u = User.objects.filter(username='nv.tb').select_related('profile__permission_group').first()
pg = u.profile.permission_group
reports = pg.get_permissions().get(MODULE_REPORTS, {})
print('Group:', pg.name)
print(json.dumps(reports, indent=2, ensure_ascii=False))
