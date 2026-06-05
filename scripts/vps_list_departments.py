import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from hrm.models import Department

for d in Department.objects.order_by('name'):
    print(f'{d.id:3} | {d.name}')
