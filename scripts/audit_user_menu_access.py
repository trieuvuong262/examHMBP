#!/usr/bin/env python3
import argparse
import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from django.contrib.auth.models import User
from hrm.menu_permissions import user_can_access_menu, user_can_access_any_menu
from hrm.module_permissions import MODULE_LABELS, get_user_enabled_modules, user_can_access_module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', required=True)
    args = parser.parse_args()

    user = User.objects.get(username=args.username)
    enabled = get_user_enabled_modules(user)
    print(f'User: {user.username}')
    print('Module access (department + role):')
    for key, label in sorted(MODULE_LABELS.items(), key=lambda x: x[1]):
        dept_ok = key in enabled
        can = user_can_access_module(user, key)
        flag = 'YES' if can else 'NO'
        dept = 'dept' if dept_ok else '---'
        print(f'  {flag:3} [{dept}] {label}')

    print('\nMenu items visible:')
    from hrm.submenu_registry import MODULE_SUBMENUS
    for module_key, entries in MODULE_SUBMENUS.items():
        for entry in entries:
            menu_key = entry['key']
            if user_can_access_menu(user, module_key, menu_key):
                print(f'  {module_key}/{menu_key}: {entry["label"]}')


if __name__ == '__main__':
    main()
