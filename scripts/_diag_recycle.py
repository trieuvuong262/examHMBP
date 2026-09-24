"""Print synoshare recycle-related help."""
from __future__ import annotations

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from nas_storage.nas_acl_apply import _run_ssh_commands

print(_run_ssh_commands(['/usr/syno/sbin/synoshare --help 2>&1 | grep -i -E "recycle|bin|trash|help" || true']))
print('--- FULL HELP ---')
print(_run_ssh_commands(['/usr/syno/sbin/synoshare --help 2>&1 | head -80']))
print('--- GET SAMPLE ---')
print(_run_ssh_commands(['/usr/syno/sbin/synoshare --get 04_KINH_DOANH_CSKH 2>&1 | head -50']))
