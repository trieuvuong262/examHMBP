#!/bin/bash
set -e
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
echo '== HTTP GET =='
curl -sI -A "$UA" https://portal.justplay.vn/accounts/login/ | head -n 12
echo '---'
curl -s -A "$UA" -o /dev/null -w "login body %{http_code} %{size_download}\n" https://portal.justplay.vn/accounts/login/
curl -s -A "$UA" -o /dev/null -w "certs dash %{http_code} %{redirect_url}\n" https://portal.justplay.vn/dashboard/certificates/
curl -s -A "$UA" -o /dev/null -w "my certs %{http_code} %{redirect_url}\n" https://portal.justplay.vn/exams/certificates/
curl -s -A "$UA" -o /dev/null -w "exams %{http_code} %{redirect_url}\n" https://portal.justplay.vn/exams/
curl -s -A "$UA" -o /dev/null -w "exam take 274 %{http_code} %{redirect_url}\n" https://portal.justplay.vn/exams/274/take/
echo '== DJANGO CLIENT =='
sed -i 's/\r$//' /tmp/_smoke_cert_exam2.py
cd /opt/portaljustplay && docker compose exec -T web python manage.py shell < /tmp/_smoke_cert_exam2.py
