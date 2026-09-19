from django.conf import settings
from django.urls import reverse
from django.test import Client
from django.contrib.auth.models import User
from assessment.certificates import layout_for_certificate
from assessment.models import Certificate, CertificateTemplate, CertificateTemplateDescription

host = [h for h in settings.ALLOWED_HOSTS if h and h != '*'][0]
admin = User.objects.filter(is_superuser=True).first()
tmpl = CertificateTemplate.objects.filter(is_default=True).first() or CertificateTemplate.objects.first()
c = Client(HTTP_HOST=host)
c.force_login(admin)
url = reverse('admin_certificate_template_edit', args=[tmpl.id])
r = c.get(url)
html = r.content.decode('utf-8', 'ignore')
print('HTTP', r.status_code, 'URL', url)
print('FORMSET', 'id_descs-TOTAL_FORMS' in html)
print('ADD_BTN', 'jp-add-desc-row' in html)
print('LABEL', 'Mô tả theo khóa học / kỳ thi' in html)
print('DEFAULT_LABEL', 'Mô tả mặc định' in html)
print('DESC_ROWS', CertificateTemplateDescription.objects.filter(template=tmpl).count())

cert = Certificate.objects.filter(code='JP-20260919-3B5CD8').select_related(
    'exam', 'exam__retry_of', 'template', 'user',
).prefetch_related('template__course_descriptions', 'exam__related_courses').first()
if cert is None:
    print('LIVE_CERT missing')
else:
    layout = layout_for_certificate(cert)
    print('LIVE_CERT', cert.code, 'score', int(cert.score), 'revoked', cert.is_revoked)
    print('LIVE_TITLE', layout.get('course_title'))
    print('LIVE_DESC_LEN', len(layout.get('description') or ''))
    print('LIVE_OK', cert.score == 90 and not cert.is_revoked)
