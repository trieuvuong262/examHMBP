#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay

echo "========== 1) .env =========="
grep -E '^(USE_HTTPS|ALLOWED_HOSTS|CSRF_TRUSTED|PORTAL_DOMAIN|SECRET_KEY)=' .env | sed 's/^SECRET_KEY=.*/SECRET_KEY=[REDACTED]/'

echo ""
echo "========== 2) Django runtime =========="
docker compose exec -T web python manage.py shell <<'PY'
import os
from django.conf import settings
ek = os.environ.get("SECRET_KEY", "")
sk = settings.SECRET_KEY
print("ENV_SECRET_LEN", len(ek))
print("DJANGO_SECRET_LEN", len(sk))
print("ENV_HAS_gvb", "gvb" in ek)
print("DJANGO_HAS_gvb", "gvb" in sk)
print("KEYS_MATCH", ek == sk)
print("ALLOWED_HOSTS", settings.ALLOWED_HOSTS)
print("CSRF_TRUSTED_ORIGINS", settings.CSRF_TRUSTED_ORIGINS)
print("USE_HTTPS", settings.USE_HTTPS)
print("CSRF_COOKIE_SECURE", settings.CSRF_COOKIE_SECURE)
print("SECURE_PROXY_SSL_HEADER", settings.SECURE_PROXY_SSL_HEADER)
PY

echo ""
echo "========== 3) CSRF curl tests =========="
test_post() {
  local label="$1"
  local url="$2"
  local referer="$3"
  local jar="/tmp/csrf_jar_${RANDOM}.txt"
  local html token code
  local curl_opts=(-s)
  [[ "$url" == https://103.90.224.203* ]] && curl_opts+=(-k)
  html=$(curl "${curl_opts[@]}" -c "$jar" -b "$jar" "$url")
  token=$(printf '%s' "$html" | sed -n 's/.*name="csrfmiddlewaretoken" value="\([^"]*\)".*/\1/p' | head -1)
  if [[ -z "$token" ]]; then
    echo "$label: NO_CSRF_TOKEN"
    return
  fi
  code=$(curl "${curl_opts[@]}" -o /dev/null -w '%{http_code}' -c "$jar" -b "$jar" -X POST "$url" \
    -H "Referer: $referer" \
    --data-urlencode "csrfmiddlewaretoken=$token" \
    --data-urlencode "username=test" \
    --data-urlencode "password=test")
  echo "$label: HTTP $code (token_len=${#token})"
  rm -f "$jar"
}

test_post "HTTPS domain login" "https://portal.justplay.vn/accounts/login/" "https://portal.justplay.vn/accounts/login/"
test_post "HTTPS IP login (-k)" "https://103.90.224.203/accounts/login/" "https://103.90.224.203/accounts/login/"
test_post "HTTPS IP bad referer http" "https://103.90.224.203/accounts/login/" "http://103.90.224.203/accounts/login/"

echo ""
echo "========== 3b) Redirect chain HTTP IP =========="
curl -sI http://103.90.224.203/accounts/login/ | grep -i location || true

echo ""
echo "========== 3c) Mismatch: token from domain, POST to IP =========="
jar="/tmp/csrf_cross.txt"
html=$(curl -s -c "$jar" -b "$jar" "https://portal.justplay.vn/accounts/login/")
token=$(printf '%s' "$html" | sed -n 's/.*name="csrfmiddlewaretoken" value="\([^"]*\)".*/\1/p' | head -1)
code=$(curl -sk -s -o /dev/null -w '%{http_code}' -c "$jar" -b "$jar" -X POST "https://103.90.224.203/accounts/login/" \
  -H "Referer: https://103.90.224.203/accounts/login/" \
  --data-urlencode "csrfmiddlewaretoken=$token" \
  --data-urlencode "username=test" \
  --data-urlencode "password=test")
echo "domain_cookie_post_ip: HTTP $code"
rm -f "$jar"

echo ""
echo "========== 4) Recent POST 403 (skipped — log lớn) =========="
echo "(skipped)"

echo ""
echo "========== 5) Docker compose SECRET_KEY warning =========="
docker compose config 2>&1 | grep -i gvb || echo "(no gvb warning in compose config)"
