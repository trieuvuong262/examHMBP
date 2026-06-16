import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from assessment.models import Exam

exam = Exam.objects.get(pk=3)
qs = exam.ordered_questions()
print('count=', qs.count())
print('sample=', list(qs.values_list('id', 'sort_order')[:5]))
