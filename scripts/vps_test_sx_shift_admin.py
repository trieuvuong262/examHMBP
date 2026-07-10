"""Test chọn ca SX với user admin trên VPS — pipe: docker compose exec -T web python manage.py shell < scripts/vps_test_sx_shift_admin.py"""
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client
from django.utils import timezone

from reports.production_shift_policy import (
    is_production_shift_assignment_choice_required,
    production_shift_assignment_for_datetime,
)

User = get_user_model()
user = User.objects.filter(username='admin').first()
if not user:
    user = User.objects.filter(is_superuser=True).first()
print('user:', user.username if user else 'NONE')

fake = timezone.localtime()
print('server_now:', fake.strftime('%H:%M %d/%m/%Y'))
print('choice_required_now:', is_production_shift_assignment_choice_required(fake))
print('auto_assign:', production_shift_assignment_for_datetime(fake))

c = Client(HTTP_HOST='portal.justplay.vn')
c.force_login(user)

r = c.get('/reports/sx/today/')
print('GET /reports/sx/today/', r.status_code)

r2 = c.post('/reports/sx/today/', {'action': 'start_product'})
print('POST start_product no shift:', r2.status_code, r2.get('Location', ''))

date_s = fake.date().isoformat()
r3 = c.post(
    f'/reports/sx/today/?date={date_s}&shift=NIGHT',
    {'action': 'start_product'},
)
loc3 = r3.get('Location', '')
print('POST start_product shift=NIGHT URL:', r3.status_code, loc3)
if r3.status_code == 302:
    r3f = c.get(loc3)
    msgs = [str(m) for m in get_messages(r3f.wsgi_request)]
    print('messages_after_night_start:', msgs[:5])
    print('still_warns_choose_shift:', any('Chọn ca' in m for m in msgs))

sim = timezone.make_aware(datetime(fake.year, fake.month, fake.day, 19, 53, 0))
with patch('reports.production_shift_policy.timezone.localtime', return_value=sim), patch(
    'django.utils.timezone.localtime', return_value=sim
), patch('reports.production_hourly.production_server_now', return_value=sim), patch(
    'reports.production_hourly.timezone.localtime', return_value=sim
):
    r4 = c.post(
        f'/reports/sx/today/?date={date_s}&shift=NIGHT',
        {'action': 'start_product'},
    )
    loc4 = r4.get('Location', '')
    print('POST 19:53 shift=NIGHT URL:', r4.status_code, loc4)
    if r4.status_code == 302:
        r4f = c.get(loc4)
        msgs4 = [str(m) for m in get_messages(r4f.wsgi_request)]
        print('19:53 messages:', msgs4[:5])
        print('19:53 still_warns:', any('Chọn ca' in m for m in msgs4))

print('DONE')
