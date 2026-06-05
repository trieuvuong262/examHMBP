"""Kiểm tra chức năng đề xuất trên VPS — chạy trong container web."""
import os
import traceback

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

from hrm.module_permissions import MODULE_DE_XUAT, user_can_access_module
from service_requests.models import RecurringItemCatalog, RequestType, ServiceRequest
from service_requests.permissions import pending_steps_for_user

User = get_user_model()

PATHS = [
    '/yeu-cau/',
    '/yeu-cau/de-xuat/cua-toi/',
    '/yeu-cau/de-xuat/cho-xu-ly/',
    '/yeu-cau/de-xuat/tao/',
    '/yeu-cau/de-xuat/danh-muc-dinh-ky/',
]


def test_user(user):
    print(f'\n=== User: {user.username} (super={user.is_superuser}) ===')
    print('  can_de_xuat:', user_can_access_module(user, MODULE_DE_XUAT))
    client = Client(HTTP_HOST='portal.justplay.vn')
    client.force_login(user)
    errors = []
    for path in PATHS:
        try:
            response = client.get(path)
            ok = response.status_code < 500
            print(f"  {'OK' if ok else 'FAIL'} {path} -> {response.status_code}")
            if response.status_code >= 500:
                body = response.content.decode('utf-8', errors='replace')[:500]
                print('   ', body)
                errors.append((path, response.status_code))
        except Exception as exc:
            print(f'  EXC {path} -> {exc}')
            traceback.print_exc()
            errors.append((path, str(exc)))

    req = (
        ServiceRequest.objects.filter(request_type__code=RequestType.CODE_ASSET_PURCHASE)
        .order_by('-id')
        .first()
    )
    if req:
        detail_path = f'/yeu-cau/de-xuat/{req.pk}/'
        response = client.get(detail_path)
        ok = response.status_code < 500
        print(f"  {'OK' if ok else 'FAIL'} detail {detail_path} -> {response.status_code}")
        if response.status_code >= 500:
            errors.append((detail_path, response.status_code))
    else:
        print('  (no asset purchase request in DB for detail test)')

    pending = (
        pending_steps_for_user(user)
        .filter(request__request_type__code=RequestType.CODE_ASSET_PURCHASE)
        .count()
    )
    print(f'  pending_steps_de_xuat: {pending}')
    return errors


def main():
    print('=== DB snapshot ===')
    print('  request_types:', list(RequestType.objects.values_list('code', 'name')))
    print(
        '  de_xuat_requests:',
        ServiceRequest.objects.filter(request_type__code=RequestType.CODE_ASSET_PURCHASE).count(),
    )
    print('  recurring_catalog:', RecurringItemCatalog.objects.filter(is_active=True).count())

    users = list(User.objects.filter(is_active=True).order_by('-is_superuser', 'id')[:5])
    if not users:
        print('NO ACTIVE USERS')
        return 1

    all_errors = []
    for user in users:
        all_errors.extend(test_user(user))

    print('\n=== Summary ===')
    if all_errors:
        print('ERRORS:', all_errors)
        return 1
    print('All tested paths OK for sampled users')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
