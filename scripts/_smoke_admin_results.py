from django.contrib import admin
from django.urls import reverse
from django.test import Client
from django.conf import settings
from django.contrib.auth.models import User
from assessment.models import ExamSubmission

print("REVERSE", reverse("admin_results"), reverse("admin:assessment_examsubmission_changelist"))
print("REGISTERED", ExamSubmission in admin.site._registry)
print("VERBOSE", ExamSubmission._meta.verbose_name_plural)

host = [h for h in settings.ALLOWED_HOSTS if h and h != "*"][0]
admin_user = User.objects.filter(is_superuser=True).first()
c = Client(HTTP_HOST=host)
c.force_login(admin_user)
r_portal = c.get(reverse("admin_results"), HTTP_HOST=host)
r_dj = c.get(reverse("admin:assessment_examsubmission_changelist"), HTTP_HOST=host)
print("HTTP portal", r_portal.status_code, "django", r_dj.status_code)
print("SIDEBAR", "Kết quả bài thi" in r_portal.content.decode("utf-8", "ignore"))
print("SMOKE_DONE")
