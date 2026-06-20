from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

HOST = 'portal.justplay.vn'

for username in ('Pkhaliem', 'Dkimchi', 'Ductn'):
    user = User.objects.get(username=username)
    c = Client()
    c.force_login(user)
    resp = c.get(reverse('my_courses'), HTTP_HOST=HOST)
    html = resp.content.decode('utf-8', errors='replace')
    urls = {
        'my_courses': reverse('my_courses') in html,
        'exam_list': reverse('exam_list') in html,
        'course_list': reverse('course_list') in html,
        'admin_assessment': reverse('admin_dashboard') + '?tab=assessment' in html,
    }
    print(f'{username}: {urls}')
