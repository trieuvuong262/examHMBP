from django.conf import settings
from django.urls import reverse
from django.test import Client
from django.contrib.auth.models import User
from assessment.models import Certificate

host = [h for h in settings.ALLOWED_HOSTS if h and h != '*'][0]
cert = (
    Certificate.objects.filter(code='JP-20260919-3B5CD8', is_revoked=False).first()
    or Certificate.objects.filter(is_revoked=False).order_by('-issued_at').first()
)
user = cert.user if cert is not None else User.objects.filter(is_superuser=True).first()
c = Client(HTTP_HOST=host)
c.force_login(user)

r = c.get(reverse('my_certificates'))
html = r.content.decode('utf-8', 'ignore')
print('HTTP_LIST', r.status_code, 'USER', user.username)
print('HAS_LINK', 'jp-my-cert-link' in html)
print('NESTED_VERIFY_A', '<a class="jp-cert-verify-link"' in html)
print('PREVIEW_SPAN', '<span class="jp-cert-verify-link"' in html)
if cert is not None:
    print('LINK_HREF', f'/exams/certificates/{cert.pk}/' in html)
    r2 = c.get(reverse('certificate_view', args=[cert.pk]))
    print('HTTP_VIEW', r2.status_code, 'PK', cert.pk, 'CODE', cert.code)
    view_html = r2.content.decode('utf-8', 'ignore')
    print('VIEW_REAL_A', '<a class="jp-cert-verify-link"' in view_html)
else:
    print('NO_CERT')
