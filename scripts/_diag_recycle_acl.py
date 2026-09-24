"""Inspect #recycle ACL and share recycle flags."""
from __future__ import annotations

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from nas_storage.nas_acl_apply import _run_ssh_commands

SHARES = (
    '02_HANH_CHINH_NHAN_SU',
    '04_KINH_DOANH_CSKH',
    '07_SAN_XUAT',
)

cmds = []
for share in SHARES:
    cmds.append(f'echo "==== SHARE {share} ===="')
    cmds.append(f'/usr/syno/sbin/synoshare --get {share} | grep -i -E "Recycle|ACL|Name|Path"')
    cmds.append(f'echo "==== ACL {share} ===="')
    cmds.append(f'/usr/syno/bin/synoacltool -get "/volume1/{share}" | head -25')
    cmds.append(f'echo "==== ACL #recycle {share} ===="')
    cmds.append(f'ls -ld "/volume1/{share}/#recycle" 2>&1 | head -3')
    cmds.append(f'/usr/syno/bin/synoacltool -get "/volume1/{share}/#recycle" 2>&1 | head -40')

cmds.append('echo "==== SMB recycle ===="')
cmds.append('grep -RIn --include="*.conf" -E "recycle|#recycle" /etc/samba /usr/syno/etc/smb* /var/tmp/nginx 2>/dev/null | head -40')
cmds.append('ls /usr/syno/etc/smb.conf* /etc/samba 2>/dev/null | head')
print(_run_ssh_commands(['\n'.join(cmds)], timeout=120))
