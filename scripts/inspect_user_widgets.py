from django.contrib.auth.models import User
u = User.objects.get(username='Ductn')
print('is_staff', u.is_staff, 'is_superuser', u.is_superuser)
