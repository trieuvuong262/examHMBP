"""Kiểm tra layout nút thao tác phiếu chuyển trên VPS."""
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
if not user:
    print('FAIL: no admin user')
    raise SystemExit(1)

client = Client(HTTP_HOST='portal.justplay.vn')
client.force_login(user)
errors = []

for tab in ('chuyen', 'nhan', 'danh-sach'):
    resp = client.get(reverse('kho_npl:transfer_hub') + f'?tab={tab}')
    html = resp.content.decode('utf-8', errors='replace')
    if resp.status_code != 200:
        errors.append(f'{tab}: HTTP {resp.status_code}')
        continue
    for needle in ('flex-nowrap', 'data-col="actions"', "key === 'actions'", 'jp-npl-transfer-row-actions', 'jp-npl-transfer-act-btn'):
        if needle not in html:
            errors.append(f'{tab}: missing {needle}')
    if f'data-transfer-tab="{tab}"' not in html:
        errors.append(f'{tab}: missing data-transfer-tab')
    if tab == 'chuyen' and '11rem' not in html:
        errors.append('chuyen: missing 11rem actions width')
    print(f'OK tab={tab} status={resp.status_code} len={len(html)}')

if errors:
    print('FAILURES:')
    for e in errors:
        print(' -', e)
    raise SystemExit(1)

print('ALL OK')
