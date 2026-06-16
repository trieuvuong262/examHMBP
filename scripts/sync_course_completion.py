#!/usr/bin/env python3
"""Đồng bộ is_completed cho mọi enrollment theo tiến độ bài học."""
import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from training.models import Enrollment


def main():
    for en in Enrollment.objects.select_related('user', 'course').order_by('course_id', 'user__username'):
        before = en.is_completed
        after = en.sync_completion_status()
        if before != after:
            print(
                f'course={en.course_id} user={en.user.username} '
                f'progress={en.progress_percent}% is_completed {before} -> {after}'
            )


if __name__ == '__main__':
    main()
