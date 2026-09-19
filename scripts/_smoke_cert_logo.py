from django.conf import settings
from django.urls import reverse
from django.test import Client
from django.contrib.auth.models import User
from assessment.models import CertificateTemplate

host = [h for h in settings.ALLOWED_HOSTS if h and h != "*"][0]
admin = User.objects.filter(is_superuser=True).first()
tmpl = CertificateTemplate.objects.filter(is_default=True).first() or CertificateTemplate.objects.first()
c = Client(HTTP_HOST=host)
c.force_login(admin)
url = reverse("admin_certificate_template_edit", args=[tmpl.id])
r = c.get(url, HTTP_HOST=host)
html = r.content.decode("utf-8", "ignore")
print("HTTP", r.status_code, "URL", url)
print("LOGO_IMG", "images/logo/logo.png" in html)
print("SEAL_CLASS", "jp-cert-seal-logo" in html)
print("OLD_TEXT_SEAL", "jp-cert-seal-ring" in html)
print("CSS_V", "certificate.css?v=20260919c" in html)
print("SMOKE_DONE")
