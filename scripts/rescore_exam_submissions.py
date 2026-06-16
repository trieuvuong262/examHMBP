#!/usr/bin/env python3
"""Tính lại điểm bài thi (sau khi sửa đề hoặc fix logic chấm)."""
import argparse
import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from assessment.models import ExamSubmission
from assessment.scoring import rescore_submission


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exam-id', type=int, default=None)
    args = parser.parse_args()

    qs = ExamSubmission.objects.filter(submitted_at__isnull=False)
    if args.exam_id:
        qs = qs.filter(exam_id=args.exam_id)

    for sub in qs.select_related('user', 'exam').order_by('exam_id', 'user__username'):
        before = sub.total_score
        result = rescore_submission(sub)
        print(
            f'exam={sub.exam_id} user={sub.user.username} '
            f'before={before} after={result["total_score"]} '
            f'auto={result["auto_score"]} manual={result["manual_score"]} '
            f'changed={result["changed_answers"]}'
        )


if __name__ == '__main__':
    main()
