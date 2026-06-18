from django.conf import settings
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid

priv = settings.WEBPUSH_VAPID_PRIVATE_KEY.encode()
pub = settings.WEBPUSH_VAPID_PUBLIC_KEY
print('pub', pub)
try:
    v = Vapid.from_pem(priv)
    from py_vapid.utils import b64urlencode
    raw_public = v.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    derived = b64urlencode(raw_public)
    print('derived_pub', derived)
    print('match', derived == pub)
except Exception as exc:
    print('from_pem_err', exc)
