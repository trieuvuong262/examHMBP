from hrm.models import Department, Division
from django.contrib.auth.models import User

for d in Department.objects.filter(is_active=True).order_by('name'):
    n = User.objects.filter(profile__department=d, profile__is_employed=True).count()
    print(d.pk, d.name, 'emp=', n)
