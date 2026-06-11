"""Đo thời gian load transfer detail trên VPS."""
import time

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse

from kho_npl.models import StockTransfer

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
if not user:
    print('FAIL: no user')
    raise SystemExit(1)

transfer = StockTransfer.objects.order_by('-pk').first()
if not transfer:
    print('FAIL: no transfer')
    raise SystemExit(1)

client = Client(HTTP_HOST='portal.justplay.vn')
client.force_login(user)

hub_url = reverse('kho_npl:transfer_hub') + '?tab=chuyen'
detail_url = reverse('kho_npl:transfer_detail', args=[transfer.pk])

for label, url in (('hub_chuyen', hub_url), ('detail', detail_url)):
    t0 = time.perf_counter()
    resp = client.get(url)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    html = resp.content.decode('utf-8', errors='replace')
    print(f'{label}: status={resp.status_code} time_ms={elapsed_ms:.1f} bytes={len(resp.content)}')
    print(f'  has_catalog_page={("jp-npl-material-catalog-page" in html)}')
    print(f'  has_jpNplCatalogLoading={("jpNplCatalogLoading" in html)}')

with override_settings(DEBUG=True):
    reset_queries()
    t0 = time.perf_counter()
    resp = client.get(detail_url)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    qcount = len(connection.queries)
    print(f'detail_debug: status={resp.status_code} time_ms={elapsed_ms:.1f} queries={qcount}')
    line_count = transfer.lines.count()
    print(f'transfer={transfer.number} lines={line_count} status={transfer.status}')
