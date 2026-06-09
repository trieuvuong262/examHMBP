from django.contrib.auth.models import User
from hrm.models import Department, ProfileConcurrentPosition

u = User.objects.get(username='Vuonglnt')
print('User:', u.username, u.profile.full_name)
print('Slots total:', ProfileConcurrentPosition.objects.filter(profile=u.profile).count())
for cp in ProfileConcurrentPosition.objects.filter(profile=u.profile):
    print(cp.pk, cp.department, cp.division, cp.role, cp.job_position, cp.is_active)

sx = Department.objects.filter(name__icontains='SẢN XUẤT') | Department.objects.filter(name__icontains='SAN XUAT')
for d in sx:
    print('Dept SX:', d.pk, d.name)
    n = User.objects.filter(profile__department=d, profile__is_employed=True).count()
    print('  employees:', n)
