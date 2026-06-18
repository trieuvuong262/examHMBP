import pywebpush
import cryptography
print('pywebpush', getattr(pywebpush, '__version__', '?'))
print('cryptography', cryptography.__version__)

from django.conf import settings
from py_vapid import Vapid
from utilities.models import MealPushSubscription

sub = MealPushSubscription.objects.first()
info = sub.subscription_info()
claims = {'sub': settings.WEBPUSH_VAPID_CLAIMS_EMAIL}
payload = '{"title":"t","body":"b"}'

pem = settings.WEBPUSH_VAPID_PRIVATE_KEY
vapid = Vapid.from_pem(pem.encode())

tests = [
    ('pem_str', pem),
    ('pem_bytes', pem.encode()),
    ('vapid_private_key', vapid.private_key),
    ('vapid_object', vapid),
]

for name, key in tests:
    try:
        pywebpush.webpush(
            subscription_info=info,
            data=payload,
            vapid_private_key=key,
            vapid_claims=claims,
        )
        print(name, 'OK')
        break
    except Exception as exc:
        print(name, type(exc).__name__, str(exc)[:120])
