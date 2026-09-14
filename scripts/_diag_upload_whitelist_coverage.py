"""Đối chiếu whitelist upload với dữ liệu thật trong DB — phát hiện chặn oan.

Chạy: python scripts/_diag_upload_whitelist_coverage.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.db.models import FileField, ImageField  # noqa: E402

from nas_storage.upload_guard import DANGEROUS_EXTS, EXT_GROUPS  # noqa: E402

counts: Counter = Counter()
for model in apps.get_models():
    fields = [
        f.name for f in model._meta.concrete_fields
        if isinstance(f, (FileField, ImageField))
    ]
    if not fields:
        continue
    try:
        rows = model._default_manager.values_list(*fields).iterator()
    except Exception:  # noqa: BLE001
        continue
    for row in rows:
        for value in row:
            if value:
                counts[PurePosixPath(str(value)).suffix.lower()] += 1

total = sum(counts.values())
ok, blocked, dangerous = [], [], []
for ext, n in counts.most_common():
    if ext in DANGEROUS_EXTS:
        dangerous.append((ext, n))
    elif ext in EXT_GROUPS:
        ok.append((ext, n))
    else:
        blocked.append((ext, n))

print('=' * 72)
print(f'DOI CHIEU WHITELIST vs DU LIEU THAT ({total} file)')
print('=' * 72)
print(f'\n[OK] duoc phep ({sum(n for _, n in ok)} file / {len(ok)} loai duoi):')
for ext, n in ok:
    print(f'   {ext:<10} {n}')
if dangerous:
    print(f'\n[CHAN — dung y] duoi nguy hiem ({sum(n for _, n in dangerous)} file):')
    for ext, n in dangerous:
        print(f'   {ext:<10} {n}')
if blocked:
    print(f'\n[!! CHAN OAN] khong nam trong whitelist ({sum(n for _, n in blocked)} file):')
    for ext, n in blocked:
        print(f'   {ext:<10} {n}   <-- xem xet bo sung vao EXT_GROUPS')
else:
    print('\n[!! CHAN OAN] khong co — whitelist phu het du lieu hien tai.')

covered = sum(n for _, n in ok)
print(f'\nTy le phu: {covered}/{total} = {100 * covered / total:.2f}%')
