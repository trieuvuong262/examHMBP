#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
NAS_HOST=$(grep -E '^NAS_SSH_HOST=' .env | cut -d= -f2- | tr -d $'\r" ')
NAS_USER=$(grep -E '^NAS_SSH_ADMIN_USER=' .env | cut -d= -f2- | tr -d $'\r" ')
NAS_PASS=$(grep -E '^NAS_SSH_ADMIN_PASSWORD=' .env | cut -d= -f2- | tr -d $'\r" ')
sshpass -p "$NAS_PASS" ssh -o StrictHostKeyChecking=no "${NAS_USER}@${NAS_HOST}" 'bash -s' <<'REMOTE'
echo "=== webdav.cfg ==="
cat /volume1/@appconf/WebDAVServer/webdav.cfg 2>/dev/null || cat /var/packages/WebDAVServer/target/etc/webdav.cfg 2>/dev/null || true
echo ""
echo "=== WebDAVServer.sc (share list) ==="
cat /volume1/@appconf/WebDAVServer/WebDAVServer.sc 2>/dev/null | head -80
echo ""
echo "=== synoshare --get 00_QUY_DINH_CHUNG ==="
synoshare --get 00_QUY_DINH_CHUNG 2>/dev/null | head -40
echo ""
echo "=== LDAP users grep Vuonglnt ==="
grep -ri "Vuonglnt\|vuonglnt" /usr/syno/etc/ldap* /etc/ldap* 2>/dev/null | head -20 || true
echo ""
echo "=== synouser --get Vuonglnt ==="
synouser --get Vuonglnt 2>/dev/null || echo "no local user Vuonglnt"
echo ""
echo "=== share acl / webdav for Vuonglnt via synoacltool if exists ==="
if command -v synoacltool >/dev/null 2>&1; then
  synoacltool get /volume1/00_QUY_DINH_CHUNG 2>/dev/null | head -30
fi
echo ""
echo "=== httpd-share-folder-alias (webdav shares) ==="
cat /var/packages/WebDAVServer/target/etc/httpd/conf/extra/httpd-share-folder-alias.conf-webdav 2>/dev/null | head -30
echo ""
echo "=== synopkg start WebDAVServer? current ==="
/usr/syno/bin/synopkg status WebDAVServer 2>/dev/null
REMOTE
