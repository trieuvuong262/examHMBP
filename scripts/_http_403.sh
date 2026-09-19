#!/bin/bash
set -e
echo '== 403 BODY =='
curl -s -A 'Mozilla/5.0' https://portal.justplay.vn/accounts/login/ | head -c 800
echo
echo '== GUNICORN LOCAL =='
cd /opt/portaljustplay
docker compose exec -T web python - << 'PY'
import urllib.request
req = urllib.request.Request('http://127.0.0.1:8000/accounts/login/', headers={'Host':'portal.justplay.vn','User-Agent':'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        print('local login', r.status, len(r.read()))
except Exception as e:
    print('local login ERR', e)
    if hasattr(e, 'code'):
        body = e.read()[:200]
        print('code', e.code, body)
PY
echo '== BLOCK CHECK =='
docker compose exec -T web python manage.py shell << 'PY'
from audit.login_security import is_ip_blocked
for ip in ['127.0.0.1','::1','103.90.224.203','172.18.0.1','172.17.0.1']:
    try:
        print(ip, is_ip_blocked(ip))
    except Exception as e:
        print(ip, 'ERR', e)
PY
echo '== WEB HEALTH =='
docker compose ps --format 'table {{.Name}}\t{{.Status}}' | head -n 20
