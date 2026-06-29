#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
NAS_HOST=$(grep -E '^NAS_SSH_HOST=' .env | cut -d= -f2- | tr -d $'\r" ')
NAS_USER=$(grep -E '^NAS_SSH_ADMIN_USER=' .env | cut -d= -f2- | tr -d $'\r" ')
NAS_PASS=$(grep -E '^NAS_SSH_ADMIN_PASSWORD=' .env | cut -d= -f2- | tr -d $'\r" ')
echo "NAS target: ${NAS_USER}@${NAS_HOST}"
if ! command -v sshpass >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sshpass
fi
sshpass -p "$NAS_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 "${NAS_USER}@${NAS_HOST}" 'bash -s' <<'REMOTE'
echo "=== DSM version ==="
grep -E "productversion|majorversion|minorversion" /etc/synoinfo.conf 2>/dev/null | head -5
echo ""
echo "=== WebDAV-related packages ==="
synopkg list 2>/dev/null | grep -i webdav || echo "(none via synopkg grep)"
echo ""
echo "=== Ports 5678 / 5006 / 443 / 80 listeners ==="
ss -tlnp 2>/dev/null | grep -E ':5678|:5006|:443 |:80 ' || netstat -tlnp 2>/dev/null | grep -E ':5678|:5006|:443 |:80 ' || true
echo ""
echo "=== WebDAV service status ==="
synoservicectl --status WebDAVServer 2>/dev/null || synoservice --status pkgctl-WebDAV 2>/dev/null || true
echo ""
echo "=== Apache vhost / WebDAV (5678) ==="
grep -RIn "5678\|WebDAV\|DavWWWRoot\|Dav\|PROPFIND\|00_QUY" /usr/local/etc/apache24/conf.d/ 2>/dev/null | head -60
echo ""
echo "=== Reverse proxy JSON ==="
if [ -f /usr/syno/etc/www/ReverseProxy.json ]; then
  python3 - <<'PY'
import json
try:
    data=json.load(open('/usr/syno/etc/www/ReverseProxy.json'))
    for item in data if isinstance(data,list) else data.get('reverse_proxy',data):
        s=str(item)
        if '5678' in s or 'webdav' in s.lower() or 'WebDAV' in s:
            print(s[:500])
except Exception as e:
    print('parse error', e)
PY
else
  echo "No ReverseProxy.json"
fi
echo ""
echo "=== Share folders (top level) ==="
ls -1 /volume1 2>/dev/null | head -20
echo ""
echo "=== Local PROPFIND test (localhost:5678) ==="
if command -v curl >/dev/null 2>&1; then
  for path in / /00_QUY_DINH_CHUNG/; do
    code=$(curl -s -k -o /dev/null -w "%{http_code}" -X PROPFIND -H "Depth: 0" "https://127.0.0.1:5678${path}" 2>/dev/null || echo ERR)
    echo "PROPFIND https://127.0.0.1:5678${path} -> ${code}"
  done
else
  echo "curl not found on NAS"
fi
REMOTE
