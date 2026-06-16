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
from documents.knowledge_base import build_user_context, build_portal_knowledge
from hrm.module_permissions import get_user_enabled_modules, MODULE_LABELS
from hrm.permissions import role_display, get_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', required=True)
    args = parser.parse_args()

    user = User.objects.get(username=args.username)
    mods = sorted(get_user_enabled_modules(user))
    print(f'User: {user.username}')
    print(f'Role: {role_display(user)}')
    profile = get_profile(user)
    if profile and profile.department:
        print(f'Dept: {profile.department.name}')
    print(f'Enabled modules ({len(mods)}):')
    for m in mods:
        print(f'  - {MODULE_LABELS.get(m, m)} ({m})')
    print('\n--- build_user_context ---')
    print(build_user_context(user))
    print('\n--- build_portal_knowledge (first 1500 chars) ---')
    ctx = build_portal_knowledge(user, question='module nao duoc phep dung')
    print(ctx[:1500])


if __name__ == '__main__':
    main()
