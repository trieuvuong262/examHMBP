"""Try a single synoacltool -replace and print output."""
from __future__ import annotations

import os
import sys

if __name__ == '__main__' and 'django' not in sys.modules:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
    import django
    django.setup()

from nas_storage.nas_acl_apply import _run_ssh_commands, _SYNOACLTOL

PATH = '/volume1/02_HANH_CHINH_NHAN_SU'
ACE = 'group:HCNS@ldap.justplay.local:allow:rwxp--aARWc--:fd--'


def main() -> None:
    print('GET BEFORE')
    print(_run_ssh_commands([f'{_SYNOACLTOL} -get "{PATH}"']))
    print('REPLACE 16')
    print(_run_ssh_commands([f'{_SYNOACLTOL} -replace "{PATH}" 16 {ACE}']))
    print('GET AFTER')
    print(_run_ssh_commands([f'{_SYNOACLTOL} -get "{PATH}"']))


if __name__ == '__main__':
    main()
