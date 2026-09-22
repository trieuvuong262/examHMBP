"""Probe synoacltool on share 04_KINH_DOANH_CSKH."""
from __future__ import annotations

import os
import sys

if __name__ == '__main__' and 'django' not in sys.modules:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
    import django
    django.setup()

from nas_storage.models import NasShareFolder
from nas_storage.nas_acl_apply import _run_ssh_commands


def main() -> None:
    folder = NasShareFolder.objects.get(pk=10)
    path = folder.resolved_volume_path()
    print('path', path)
    cmds = [
        f'/usr/syno/bin/synoacltool -help 2>&1 | head -80',
        f'/usr/syno/bin/synoacltool -get "{path}" 2>&1 | head -60',
        f'/usr/syno/sbin/synoshare --list_acl {folder.share_name} 2>&1 | head -40',
    ]
    out = _run_ssh_commands(cmds, timeout=60)
    print(out)


if __name__ == '__main__':
    main()
