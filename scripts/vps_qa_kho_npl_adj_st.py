"""QA điều chỉnh + kiểm kê + hủy phiếu — Ductn trên VPS."""
import sys
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from kho_npl.choices import (
    ADJUST_STATUS_APPROVED,
    ADJUST_STATUS_PENDING,
    ADJUST_STATUS_REJECTED,
    DOC_STATUS_CANCELLED,
    DOC_STATUS_DRAFT,
    STOCKTAKE_STATUS_CLOSED,
    STOCKTAKE_STATUS_COUNTING,
)
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockAdjustment,
    StockBalance,
    StockReceipt,
    Stocktake,
    StocktakeLine,
    Unit,
    WarehouseLocation,
)

User = get_user_model()
HOST = 'portal.justplay.vn'
FAIL = []
TS = timezone.now().strftime('%H%M%S')
ductn = User.objects.get(username='Ductn')
client = Client(HTTP_HOST=HOST)
client.force_login(ductn)

cat = MaterialCategory.objects.filter(is_active=True).first()
unit = Unit.objects.filter(is_active=True).first()
loc = WarehouseLocation.objects.get(code='MAIN')

mat = Material.objects.create(code=f'AS-{TS}', name='QA adj/st', category=cat, unit=unit)
StockBalance.objects.create(material=mat, location=loc, quantity=Decimal('20'))

# Điều chỉnh: duyệt
adj = StockAdjustment.objects.create(
    number=f'DC-HQ-{TS}', adjust_date=timezone.localdate(),
    material=mat, location=loc, system_qty=Decimal('20'), actual_qty=Decimal('18'),
    reason='QA test', proposed_by=ductn, status=ADJUST_STATUS_PENDING,
)
r = client.post(reverse('kho_npl:adjustment_approve', args=[adj.pk]))
adj.refresh_from_db()
bal = StockBalance.objects.get(material=mat, location=loc)
if r.status_code == 302 and adj.status == ADJUST_STATUS_APPROVED and bal.quantity == Decimal('18'):
    print('  PASS: adjustment approve')
else:
    FAIL.append('adjustment approve')

# Điều chỉnh: từ chối
adj2 = StockAdjustment.objects.create(
    number=f'DC-HQ2-{TS}', adjust_date=timezone.localdate(),
    material=mat, location=loc, system_qty=Decimal('18'), actual_qty=Decimal('99'),
    reason='QA reject', proposed_by=ductn, status=ADJUST_STATUS_PENDING,
)
r = client.post(reverse('kho_npl:adjustment_reject', args=[adj2.pk]), {'note': 'Sai số'})
adj2.refresh_from_db()
if r.status_code == 302 and adj2.status == ADJUST_STATUS_REJECTED:
    print('  PASS: adjustment reject')
else:
    FAIL.append('adjustment reject')

# Kiểm kê: chốt
st = Stocktake.objects.create(
    number=f'KK-HQ-{TS}', name='QA stocktake', stocktake_date=timezone.localdate(),
    created_by=ductn, status=STOCKTAKE_STATUS_COUNTING,
)
StocktakeLine.objects.create(stocktake=st, material=mat, location=loc,
                             system_qty=Decimal('18'), actual_qty=Decimal('17'))
from kho_npl.services.stocktakes import close_stocktake
close_stocktake(st, ductn)
bal.refresh_from_db()
st.refresh_from_db()
if st.status == STOCKTAKE_STATUS_CLOSED and bal.quantity == Decimal('17'):
    print('  PASS: stocktake close')
else:
    FAIL.append(f'stocktake close status={st.status} qty={bal.quantity}')

# Hủy phiếu nhập nháp
rcp = StockReceipt.objects.create(
    number=f'PN-CAN-{TS}', receipt_date=timezone.localdate(),
    created_by=ductn, status=DOC_STATUS_DRAFT,
)
r = client.post(reverse('kho_npl:receipt_cancel', args=[rcp.pk]))
rcp.refresh_from_db()
if r.status_code == 302 and rcp.status == DOC_STATUS_CANCELLED:
    print('  PASS: receipt cancel draft')
else:
    FAIL.append('receipt cancel')

# Cleanup
from kho_npl.models import StockLedger
StockLedger.objects.filter(material=mat).delete()
StockAdjustment.objects.filter(material=mat).delete()
Stocktake.objects.filter(pk=st.pk).delete()
StockReceipt.objects.filter(pk=rcp.pk).delete()
StockBalance.objects.filter(material=mat).delete()
mat.delete()
print('  PASS: cleanup')

print('RESULT:', 'OK' if not FAIL else 'FAILED', FAIL)
sys.exit(1 if FAIL else 0)
