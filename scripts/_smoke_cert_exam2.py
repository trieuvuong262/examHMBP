"""Smoke test certificate + exam integrity after deploy (HTTP_HOST aware)."""
from django.conf import settings
from django.urls import reverse
from django.test import Client
from django.contrib.auth.models import User

from assessment.models import CertificateTemplate, Exam, Certificate
from hrm.permissions import is_portal_admin
from training.models import Course

hosts = [h for h in settings.ALLOWED_HOSTS if h and h != "*"]
host = hosts[0] if hosts else "portal.justplay.vn"
print("HOST", host, "ALLOWED", settings.ALLOWED_HOSTS[:8])
print(
    "REVERSE",
    reverse("admin_certificate_list"),
    reverse("my_certificates"),
    reverse("take_exam", args=[1]),
)
print(
    "TEMPLATES",
    CertificateTemplate.objects.count(),
    "default",
    CertificateTemplate.objects.filter(is_default=True).exists(),
)
print("CERTS", Certificate.objects.count())

needles = [
    "examPledge",
    "examIntegrityGuard",
    "js-essay-answer",
    "examCopyGuard",
    "Chỉ phản hồi đáp án đúng",
    "Không được dán",
    "Tôi cam kết làm bài trung thực",
]

admin = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
print("ADMIN", getattr(admin, "username", None), "portal_admin", bool(admin and is_portal_admin(admin)))

course = Course.objects.filter(id__in=(4, 5, 6, 7), final_exam__isnull=False).first()
exam = course.final_exam if course else Exam.objects.filter(issue_certificate=True).order_by("-id").first()
print(
    "EXAM",
    getattr(exam, "id", None),
    getattr(exam, "title", None),
    "issue",
    getattr(exam, "issue_certificate", None),
)

c = Client(HTTP_HOST=host)
if admin:
    c.force_login(admin)

    def g(url):
        return c.get(url, HTTP_HOST=host)

    r_list = g(reverse("admin_certificate_list"))
    r_tmpl = g(reverse("admin_certificate_templates"))
    r_dash = g(reverse("admin_dashboard") + "?tab=assessment")
    print("HTTP list", r_list.status_code, "tmpl", r_tmpl.status_code, "dash", r_dash.status_code)
    dash_html = r_dash.content.decode("utf-8", "ignore")
    print("DASH_CERT_BTN", "admin_certificate_list" in dash_html or "Chứng chỉ" in dash_html)
    if exam:
        r_edit = g(reverse("exam_edit", args=[exam.id]))
        edit_html = r_edit.content.decode("utf-8", "ignore")
        print("HTTP exam_edit", r_edit.status_code, "issueCertSwitch", "issueCertSwitch" in edit_html)
        r_take = g(reverse("take_exam", args=[exam.id]))
        print("HTTP take_exam", r_take.status_code)
        html = r_take.content.decode("utf-8", "ignore")
        if r_take.status_code in (301, 302):
            print("TAKE_REDIRECT", r_take.get("Location"))
        else:
            for n in needles:
                print("NEEDLE", n, n in html)
            if r_take.status_code >= 400:
                print("TAKE_SNIP", html[:400].replace("\n", " "))
    r_mine = g(reverse("my_certificates"))
    print("HTTP my_certificates", r_mine.status_code)
    if r_mine.status_code in (301, 302):
        print("MINE_REDIRECT", r_mine.get("Location"))

print("SMOKE_DONE")
