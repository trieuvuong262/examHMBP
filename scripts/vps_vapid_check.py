from django.conf import settings
k = settings.WEBPUSH_VAPID_PRIVATE_KEY
print('len', len(k))
print('repr_start', repr(k[:50]))
print('real_newlines', k.count('\n'))
print('has_literal_backslash_n', '\\n' in k)
try:
    from pywebpush import webpush
    from utilities.models import MealPushSubscription
    sub = MealPushSubscription.objects.first()
    if sub:
        webpush(
            subscription_info=sub.subscription_info(),
            data='{"title":"t","body":"b"}',
            vapid_private_key=k,
            vapid_claims={'sub': settings.WEBPUSH_VAPID_CLAIMS_EMAIL},
        )
        print('webpush', 'OK')
except Exception as exc:
    print('webpush_err', type(exc).__name__, str(exc)[:300])
