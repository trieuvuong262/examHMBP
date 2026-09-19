from training.models import Course
from assessment.models import Exam, Certificate, CertificateTemplate

print("COURSES")
for c in Course.objects.filter(id__in=(4, 5, 6, 7)).order_by("id"):
    ex = c.final_exam
    print(c.id, c.title, "exam", getattr(ex, "id", None), getattr(ex, "title", None), "issue", getattr(ex, "issue_certificate", None), "pass", getattr(ex, "pass_score", None))
print("TEMPLATES", CertificateTemplate.objects.filter(is_default=True).count(), "CERTS", Certificate.objects.count())
print("OK")
