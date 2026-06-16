#!/usr/bin/env python3
"""In lịch sử hỏi đáp Thư viện của một user."""
import argparse
import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from django.contrib.auth.models import User
from documents.models import LibraryQAChatMessage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', required=True)
    parser.add_argument('--limit', type=int, default=50)
    args = parser.parse_args()

    user = User.objects.get(username=args.username)
    msgs = (
        LibraryQAChatMessage.objects.filter(user=user)
        .order_by('created_at')[: args.limit]
    )
    print(f'User: {user.username} (id={user.id})')
    print(f'Messages: {msgs.count()} shown (max {args.limit})')
    print('-' * 80)

    turn = 0
    pending_q = None
    for m in msgs:
        if m.role == LibraryQAChatMessage.ROLE_USER:
            turn += 1
            pending_q = m.text
            print(f'\n[{turn}] USER @ {m.created_at:%Y-%m-%d %H:%M}')
            print(m.text)
        elif m.role == LibraryQAChatMessage.ROLE_MODEL:
            print(f'    BOT @ {m.created_at:%Y-%m-%d %H:%M}')
            print(m.text)
            if pending_q:
                pending_q = None


if __name__ == '__main__':
    main()
