"""HTTP form workflow qua Django Client — user Ductn trên VPS."""
import sys
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_POSTED
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockBalance,
    StockIssue,
    StockReceipt,
    Unit,
    WarehouseLocation,
)

User = get_user_model()
HOST = 'portal.justplay.vn'
PREFIX = 'HTTP-QA'
FAIL = []
TS = timezone.now().strftime('%H%M%S')


def ok(msg):
    print(f'  PASS: {msg}')


def fail(msg, detail=''):
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' — {detail}' if detail else ''))


ductn = User.objects.get(username='Ductn')
client = Client(HTTP_HOST=HOST)
client.force_login(ductn)

category = MaterialCategory.objects.filter(is_active=True).first()
unit = Unit.objects.filter(is_active=True).first()
location = WarehouseLocation.objects.get(code='MAIN')
mat_code = f'HQ-{TS}'

print('=== HTTP POST — Tạo NPL (Ductn) ===')
r = client.post(reverse('kho_npl:material_create'), {
    'code': mat_code,
    'name': f'{PREFIX} Vai test',
    'category': category.pk,
    'unit': unit.pk,
    'min_stock': '5',
    'is_active': 'on',
})
if r.status_code == 302:
    ok('POST material_create → 302')
else:
    fail('POST material_create', f'status={r.status_code}')

mat = Material.objects.filter(code__icontains=mat_code.replace('-', '')).first()
if not mat:
    mat = Material.objects.filter(name__contains=PREFIX).order_by('-pk').first()
if mat:
    ok(f'NPL created: {mat.code}')
else:
    fail('NPL not found after create')

print('=== HTTP POST — Phiếu nhập + ghi sổ ===')
r = client.get(reverse('kho_npl:receipt_create'))
if r.status_code != 200:
    fail('GET receipt_create', str(r.status_code))
else:
    ok('GET receipt_create form')

# Tạo receipt qua ORM rồi ghi sổ qua HTTP (formset phức tạp)
if mat:
    receipt = StockReceipt.objects.create(
        number=f'PN-HQ-{TS}',
        receipt_date=timezone.localdate(),
        created_by=ductn,
        status='draft',
    )
    from kho_npl.models import StockReceiptLine
    StockReceiptLine.objects.create(
        receipt=receipt, material=mat, location=location,
        received_qty=Decimal('50'),
    )
    r = client.post(reverse('kho_npl:receipt_post', args=[receipt.pk]))
    if r.status_code == 302:
        receipt.refresh_from_db()
        if receipt.status == DOC_STATUS_POSTED:
            ok('POST receipt_post → ghi sổ')
        else:
            fail('receipt_post', f'status={receipt.status}')
    else:
        fail('POST receipt_post', str(r.status_code))

    bal = StockBalance.objects.filter(material=mat, location=location).first()
    if bal and bal.quantity == Decimal('50'):
        ok('Tồn = 50 sau nhập')
    else:
        fail('Balance after receipt', str(bal.quantity if bal else None))

print('=== HTTP POST — Phiếu xuất + ghi sổ ===')
if mat:
    from kho_npl.choices import ISSUE_TYPE_PRODUCTION
    issue = StockIssue.objects.create(
        number=f'PX-HQ-{TS}',
        issue_date=timezone.localdate(),
        issue_type=ISSUE_TYPE_PRODUCTION,
        created_by=ductn,
        status='draft',
    )
    from kho_npl.models import StockIssueLine
    StockIssueLine.objects.create(issue=issue, material=mat, location=location, quantity=Decimal('10'))
    r = client.post(reverse('kho_npl:issue_post', args=[issue.pk]))
    if r.status_code == 302:
        issue.refresh_from_db()
        bal = StockBalance.objects.get(material=mat, location=location)
        if issue.status == DOC_STATUS_POSTED and bal.quantity == Decimal('40'):
            ok('POST issue_post → tồn = 40')
        else:
            fail('issue_post result', f'status={issue.status} qty={bal.quantity}')
    else:
        fail('POST issue_post', str(r.status_code))

print('=== Cleanup ===')
if mat:
    from kho_npl.models import StockLedger
    StockLedger.objects.filter(material=mat).delete()
    StockReceipt.objects.filter(number__startswith='PN-HQ-').delete()
    StockIssue.objects.filter(number__startswith='PX-HQ-').delete()
    StockBalance.objects.filter(material=mat).delete()
    mat.delete()
    ok('Cleaned HTTP-QA data')

print('\nRESULT:', 'OK' if not FAIL else 'FAILED')
for f in FAIL:
    print('  •', f)
sys.exit(1 if FAIL else 0)
