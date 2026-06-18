from django.contrib.auth import get_user_model
from utilities.models import MealPushSubscription
from utilities.push_service import send_test_meal_push, send_push_to_subscription, _test_meal_push_payload

u = get_user_model().objects.get(username='admin')
subs = list(MealPushSubscription.objects.filter(user=u))
print('subs', len(subs))
for s in subs:
    print('id', s.pk)
    print('endpoint', s.endpoint[:100])
    print('ua', (s.user_agent or '')[:80])
    try:
        send_push_to_subscription(s, _test_meal_push_payload())
        print('direct_send', 'OK')
    except Exception as exc:
        print('direct_send', type(exc).__name__, str(exc)[:300])
        resp = getattr(exc, 'response', None)
        if resp is not None:
            print('status', getattr(resp, 'status_code', None))
            print('body', getattr(resp, 'text', '')[:200])

stats = send_test_meal_push(u)
print('stats', stats)
