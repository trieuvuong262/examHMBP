#!/usr/bin/env bash
# Rà soát vector tấn công còn lại trên VPS
set -euo pipefail
cd /opt/portaljustplay

echo "=== METABASE ==="
docker ps -a 2>/dev/null | grep -i meta || echo "OK: không còn metabase"

echo ""
echo "=== PORTS PUBLIC ==="
ss -tlnp | grep -E '0.0.0.0:|\\[::\\]:' | grep -v '127.0.0.1' || true

echo ""
echo "=== ENDPOINT PROBE (local nginx) ==="
probe() {
  local path="$1"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: portal.justplay.vn' "http://127.0.0.1${path}" || echo 'ERR')
  printf '  %-35s %s\n' "$path" "$code"
}
probe '/accounts/login/'
probe '/admin/'
probe '/.env'
probe '/.git/config'
probe '/wp-admin/'
probe '/phpmyadmin/'
probe '/ckeditor/upload/'
probe '/robots.txt'

echo ""
echo "=== NGINX TOP PATHS (72h, status 4xx/5xx) ==="
docker compose logs nginx --since 72h 2>/dev/null \
  | grep -E '"(GET|POST|HEAD) ' \
  | grep -E ' (404|403|401|500|502) ' \
  | sed -E 's/.*"(GET|POST|HEAD) ([^ ]+) .*/\2/' \
  | sort | uniq -c | sort -rn | head -20 || true

echo ""
echo "=== NGINX LOGIN POST (72h) ==="
docker compose logs nginx --since 72h 2>/dev/null | grep -c 'POST /accounts/login' || echo 0

echo ""
echo "=== PORTAL LOGIN FAILED (7 ngày) ==="
docker compose exec -T web python manage.py shell -c "
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count
from audit.models import UserActivityLog
since = timezone.now() - timedelta(days=7)
qs = UserActivityLog.objects.filter(created_at__gte=since, action='login_failed')
print('total failed:', qs.count())
for row in qs.values('ip_address').annotate(c=Count('id')).order_by('-c')[:10]:
    print(row)
for r in qs.order_by('-created_at')[:8]:
    print(r.created_at.astimezone().strftime('%d/%m %H:%M'), r.username, r.ip_address)
" 2>/dev/null || echo "skip audit query"

echo ""
echo "=== SSH SINCE HARDEN (password success) ==="
journalctl -u ssh --since '2026-06-08 09:14:00' 2>/dev/null | grep -ci 'Accepted password' || echo 0

echo ""
echo "=== UFW SSH WHITELIST ==="
ufw status 2>/dev/null | grep -E '22|Status' || echo "ufw n/a"

echo ""
echo "=== FAIL2BAN ==="
fail2ban-client status sshd 2>/dev/null || echo "fail2ban n/a"

echo ""
echo "=== DONE ==="
