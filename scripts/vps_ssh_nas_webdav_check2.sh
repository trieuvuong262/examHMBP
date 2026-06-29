#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
NAS_HOST=$(grep -E '^NAS_SSH_HOST=' .env | cut -d= -f2- | tr -d $'\r" ')
NAS_USER=$(grep -E '^NAS_SSH_ADMIN_USER=' .env | cut -d= -f2- | tr -d $'\r" ')
NAS_PASS=$(grep -E '^NAS_SSH_ADMIN_PASSWORD=' .env | cut -d= -f2- | tr -d $'\r" ')
sshpass -p "$NAS_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 "${NAS_USER}@${NAS_HOST}" 'bash -s' <<'REMOTE'
echo "=== Process on 5678 ==="
if command -v lsof >/dev/null 2>&1; then lsof -iTCP:5678 -sTCP:LISTEN 2>/dev/null || true; fi
netstat -tlnp 2>/dev/null | grep 5678 || true
echo ""
echo "=== synoinfo / webdav settings ==="
grep -i webdav /etc/synoinfo.conf 2>/dev/null || true
grep -ri "5678" /usr/syno/etc/ 2>/dev/null | head -30
grep -ri "5678" /etc/nginx/ 2>/dev/null | head -30
echo ""
echo "=== Installed packages (web/file) ==="
synopkg list 2>/dev/null | grep -iE "WebDAV|FileStation|Apache|nginx" | head -20
echo ""
echo "=== Apache sites ==="
ls -la /usr/local/etc/apache24/sites-enabled/ 2>/dev/null | head -20
ls -la /usr/local/etc/apache24/conf.d/ 2>/dev/null | head -20
echo ""
echo "=== DSM WebDAV config files ==="
find /usr/syno/etc -maxdepth 3 -iname '*webdav*' 2>/dev/null
find /var/packages -maxdepth 2 -iname '*WebDAV*' 2>/dev/null
echo ""
echo "=== cat webdav settings if exist ==="
for f in /usr/syno/etc/webdav.conf /usr/syno/etc/webdav/webdav.conf /var/packages/WebDAVServer/etc/webdav.conf; do
  [ -f "$f" ] && echo "--- $f ---" && cat "$f" 2>/dev/null
done
echo ""
echo "=== nginx server blocks 5678 ==="
grep -RIn "5678" /etc/nginx /usr/syno/etc/nginx 2>/dev/null | head -40
echo ""
echo "=== Authenticated PROPFIND (admin local) ==="
# use admin DSM password from stdin not available - test OPTIONS only
for path in / /00_QUY_DINH_CHUNG/; do
  echo "--- OPTIONS $path ---"
  curl -s -k -I -X OPTIONS "https://127.0.0.1:5678${path}" 2>/dev/null | tr -d '\r' | grep -iE 'HTTP/|Allow:|DAV:|Server:'
done
echo ""
echo "=== smb webdav alternative ports ==="
synogetkeyvalue /usr/syno/etc/www-service.conf 2>/dev/null | head -5 || true
cat /usr/syno/etc/www/DSM.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d,indent=2)[:3000])" 2>/dev/null || true
REMOTE
