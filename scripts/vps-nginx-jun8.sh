#!/usr/bin/env bash
# Phân tích nginx ngày 8/6 (VN = UTC+7)
cd /opt/portaljustplay
START='2026-06-07T17:00:00'
END='2026-06-08T17:00:00'
LOG=$(docker compose logs nginx --since "$START" --until "$END" 2>/dev/null)

echo "=== NGINX 8/6 VN - TONG ==="
echo "Total requests: $(echo "$LOG" | grep -cE 'HTTP/1\.[01]"' || echo 0)"
echo "Suspicious (.env/wp/cgi/php): $(echo "$LOG" | grep -ciE '\.env|wp-admin|php://|cgi-bin|\.git' || echo 0)"
echo "POST /accounts/login: $(echo "$LOG" | grep -c 'POST /accounts/login' || echo 0)"
echo "Status 200 suspicious: $(echo "$LOG" | grep -iE '\.env|wp-admin' | grep -c ' 200 ' || echo 0)"

echo ""
echo "=== TOP PATH BI QUET (4xx) ==="
echo "$LOG" | grep -E ' (404|403|400) ' | grep -oE '(GET|POST) [^ ]+' | awk '{print $2}' | sort | uniq -c | sort -rn | head -15

echo ""
echo "=== TOP IP QUET WEB 8/6 ==="
echo "$LOG" | grep -oE '^[0-9.]+' | sort | uniq -c | sort -rn | head -12

echo ""
echo "=== MAU TAN CONG CUOI NGAY 8/6 (VN sang) ==="
echo "$LOG" | grep -iE '\.env|php://|cgi-bin|wp-admin' | tail -12
