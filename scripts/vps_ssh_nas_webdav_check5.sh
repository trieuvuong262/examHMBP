#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
NAS_HOST=$(grep -E '^NAS_SSH_HOST=' .env | cut -d= -f2- | tr -d $'\r" ')
NAS_USER=$(grep -E '^NAS_SSH_ADMIN_USER=' .env | cut -d= -f2- | tr -d $'\r" ')
NAS_PASS=$(grep -E '^NAS_SSH_ADMIN_PASSWORD=' .env | cut -d= -f2- | tr -d $'\r" ')
sshpass -p "$NAS_PASS" ssh -o StrictHostKeyChecking=no "${NAS_USER}@${NAS_HOST}" 'bash -s' <<'REMOTE'
echo "=== Try start WebDAVServer ==="
/usr/syno/bin/synopkg start WebDAVServer 2>&1 | head -10
sleep 3
/usr/syno/bin/synopkg status WebDAVServer 2>&1
echo ""
echo "=== share_right.map Vuonglnt / IT groups ==="
grep -n "Vuonglnt\|vuonglnt\|10_HE_THONG_CNTT\|HCNS" /usr/syno/etc/share_right.map 2>/dev/null | head -40
echo ""
echo "=== synogroup --list (IT related) ==="
synogroup --list 2>/dev/null | grep -iE "IT|HCNS|LDAP|domain" | head -20 || true
REMOTE
