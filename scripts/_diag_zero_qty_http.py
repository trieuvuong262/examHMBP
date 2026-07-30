"""HTTP smoke: chi tiết BC có công đoạn SL=0."""
from django.contrib.auth import get_user_model
from django.test import Client

from reports.models import DailyWorkReport
from reports.production_hourly import build_productivity_report

User = get_user_model()
admin = User.objects.filter(is_superuser=True).order_by('id').first()
client = Client()
client.force_login(admin)

for pk in (4789, 4765, 4681, 4873):
    report = DailyWorkReport.objects.get(pk=pk)
    prod = build_productivity_report(report)
    zero_rows = [
        s for s in prod['product_summaries']
        if s.get('is_zero_reason_only') or s.get('quantity') == 0
    ]
    resp = client.get(f'/reports/sx/{pk}/', HTTP_HOST='portal.justplay.vn')
    html = resp.content.decode('utf-8', errors='replace')
    has_summary = 'jp-prod-summary-row' in html
    zero_tr = html.count('is-zero-qty')
    has_zero_text = 'Sản lượng 0' in html
    print(
        f'HTTP pk={pk} status={resp.status_code} '
        f'summaries={len(prod["product_summaries"])} zero_rows={len(zero_rows)} '
        f'has_summary={has_summary} zero_tr={zero_tr} has_zero_text={has_zero_text}'
    )
    for s in zero_rows[:4]:
        print(
            '  SL0:',
            s.get('product_code'),
            '|',
            s.get('process_name'),
            '| eff=',
            s.get('efficiency_pct'),
            '| hours=',
            s.get('hours_display'),
        )
