from django.contrib.auth import get_user_model
from utilities.models import MealPushSubscription

u = get_user_model().objects.get(username='admin')
n, _ = MealPushSubscription.objects.filter(user=u).delete()
print('deleted', n)
