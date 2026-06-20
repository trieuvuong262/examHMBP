from django.contrib.auth.models import User
from utilities.portal_push_eligibility import user_portal_push_debug, user_portal_push_eligible

u = User.objects.get(username='Ductn')
print('Ductn push_debug', user_portal_push_debug(u), 'push_eligible', user_portal_push_eligible(u))
