"""Smoke test certificate + exam integrity after deploy."""
from django.urls import reverse
from django.test import Client
from django.contrib.auth.models import User

from assessment.models import CertificateTemplate, Exam
from hrm.permissions import is_portal_admin
from training.models import Course

print('REVERSE', reverse('admin_certificate_list'), reverse('my_certificates'), reverse('take_exam', args=[1]))
print('TEMPLATES', CertificateTemplate.objects.count(), 'default', CertificateTemplate.objects.filter(is_default=True).exists())

needles = [
    'examPledge',
    'examIntegrityGuard',
    'js-essay-answer',
    'examCopyGuard',
    'Chỉ phản hồi đáp án đúng',
    'Không được dán',
    'Tôi cam kết làm bài trung thực',
]

admin = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
print('ADMIN', admin.username if admin else None, 'portal_admin', bool(admin and is_portal_admin(admin)))

course = Course.objects.filter(id__in=(4, 5, 6, 7), final_exam__isnull=False).first()
exam = course.final_exam if course else Exam.objects.filter(issue_certificate=True).order_by('-id').first()
print('EXAM', exam.id if exam else None, exam.title if exam else None)

c = Client()
if admin:
    c.force_login(admin)
    r_list = c.get(reverse('admin_certificate_list'))
    r_tmpl = c.get(reverse('admin_certificate_templates'))
    r_dash = c.get(reverse('admin_dashboard') + '?tab=assessment')
    print('HTTP list', r_list.status_code, 'tmpl', r_tmpl.status_code, 'dash', r_dash.status_code)
    dash_html = r_dash.content.decode('utf-8', 'ignore')
    print('DASH_CERT_BTN', 'admin_certificate_list' in dash_html or 'Chứng chỉ' in dash_html)
    if exam:
        r_edit = c.get(reverse('exam_edit', args=[exam.id]))
        edit_html = r_edit.content.decode('utf-8', 'ignore')
        print('HTTP exam_edit', r_edit.status_code, 'issueCertSwitch', 'issueCertSwitch' in edit_html)
        r_take = c.get(reverse('take_exam', args=[exam.id]))
        print('HTTP take_exam', r_take.status_code)
        html = r_take.content.decode('utf-8', 'ignore')
        if r_take.status_code in (301, 302):
            print('TAKE_REDIRECT', r_take.get('Location'))
        else:
            for n in needles:
                print('NEEDLE', n, n in html)

    r_mine = c.get(reverse('my_certificates'))
    print('HTTP my_certificates', r_mine.status_code)

print('SMOKE_DONE')
