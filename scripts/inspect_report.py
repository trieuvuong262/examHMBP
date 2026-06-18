import re
import sys

from django.core.files.storage import default_storage

from reports.models import DailyWorkReport

pk = 41
r = DailyWorkReport.objects.filter(pk=pk).first()
if not r:
    print('NO_REPORT')
    raise SystemExit(1)

print('profile', r.report_profile, 'status', r.status, 'hod', r.hod_reviewed)
html = r.document_html or ''
print('html_len', len(html))
print('html_snippet', html[:3000])
imgs = re.findall(r'<img[^>]+>', html, re.I)
print('img_count', len(imgs))
for i, img in enumerate(imgs[:10]):
    print('IMG', i, img[:800])
atts = list(r.attachments.all())
print('attachments', len(atts))
for a in atts:
    exists = default_storage.exists(a.file.name) if not a.file.name.startswith('reports/daily/') else 'nas'
    print('ATT', a.pk, a.source_tab, a.kind, a.file.name, 'exists', exists)

for img in imgs:
    for attr in ('src', 'data-cke-saved-src'):
        m = re.search(rf'{attr}=["\']([^"\']+)["\']', img, re.I)
        if m:
            url = m.group(1)
            print('URL', attr, url)
            if 'reports/ckeditor5/' in url:
                rel = url.split('reports/ckeditor5/', 1)[-1].split('?', 1)[0]
                rel = f'reports/ckeditor5/{rel}'
                print('  storage_exists', default_storage.exists(rel), rel)
