"""Try deleting empty-name synoacl ACEs and print NAS output."""
from __future__ import annotations

import os
import sys

if __name__ == '__main__' and 'django' not in sys.modules:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
    import django
    django.setup()

from nas_storage.nas_acl_apply import _SYNOACLTOL, _run_ssh_commands, parse_synoacl_get

PATH = '/volume1/02_HANH_CHINH_NHAN_SU'


def main() -> None:
    get_cmd = f'{_SYNOACLTOL} -get "{PATH}"'
    before = _run_ssh_commands([get_cmd])
    print('=== BEFORE ===')
    print(before)
    rows = parse_synoacl_get(before)
    empties = [r for r in rows if r['level'] == 0 and not r['name']]
    print('EMPTY', [(r['index'], r['kind'], r['perm']) for r in empties])
    if not empties:
        return
    idx = max(r['index'] for r in empties)
    del_cmd = f'{_SYNOACLTOL} -del "{PATH}" {idx}'
    print('DEL', del_cmd)
    print('=== DEL OUT ===')
    print(_run_ssh_commands([del_cmd]))
    print('=== AFTER ===')
    print(_run_ssh_commands([get_cmd]))


if __name__ == '__main__':
    main()
