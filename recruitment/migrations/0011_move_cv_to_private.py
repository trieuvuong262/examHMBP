"""Chuyển CV cũ (media công khai /media/candidate_cvs/) sang kho riêng tư.

File được sao chép vào ``MEDIA_ROOT/_private/recruitment/`` (tên UUID) rồi xóa bản
công khai — sau migration không còn đường dẫn /media/ trỏ tới CV ứng viên.
"""

import os
import uuid

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.db import migrations

TYPES = {'.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx'}


def forward(apps, schema_editor):
    Candidate = apps.get_model('recruitment', 'Candidate')
    CandidateFile = apps.get_model('recruitment', 'CandidateFile')
    public = FileSystemStorage(location=settings.MEDIA_ROOT)
    private = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, '_private', 'recruitment'))

    for cand in Candidate.objects.exclude(cv_file='').exclude(cv_file__isnull=True):
        name = cand.cv_file.name
        if not public.exists(name):
            continue
        ext = os.path.splitext(name)[1].lower()
        ext = ext if ext in TYPES else '.bin'
        new_name = f'cv/legacy/{uuid.uuid4().hex}{ext}'
        with public.open(name, 'rb') as fh:
            saved = private.save(new_name, File(fh))
        CandidateFile.objects.create(
            candidate=cand, kind='cv', file=saved,
            original_name=os.path.basename(name)[:255], size=private.size(saved),
            uploaded_at=cand.applied_at,
        )
        public.delete(name)


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0010_candidate_files'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
