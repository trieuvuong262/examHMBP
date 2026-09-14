"""Liệt kê phần mở rộng file đang thực dùng trong DB — để lập whitelist đúng nghiệp vụ.

Chạy: python scripts/_diag_upload_extensions.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from pathlib import PurePosixPath

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.db.models import FileField, ImageField  # noqa: E402

per_field: dict[str, Counter] = defaultdict(Counter)
overall = Counter()

for model in apps.get_models():
    fields = [
        f.name for f in model._meta.concrete_fields
        if isinstance(f, (FileField, ImageField))
    ]
    if not fields:
        continue
    label = model._meta.label
    try:
        rows = model._default_manager.values_list(*fields).iterator()
    except Exception as exc:  # noqa: BLE001
        print(f'  (bo qua {label}: {exc})')
        continue
    for row in rows:
        for idx, value in enumerate(row):
            if not value:
                continue
            ext = PurePosixPath(str(value)).suffix.lower() or '(khong co)'
            per_field[f'{label}.{fields[idx]}'][ext] += 1
            overall[ext] += 1

print('=' * 78)
print('PHAN MO RONG DANG DUNG — THEO TUNG TRUONG')
print('=' * 78)
for key in sorted(per_field):
    counter = per_field[key]
    total = sum(counter.values())
    detail = ', '.join(f'{e}={c}' for e, c in counter.most_common())
    print(f'\n{key}  (tong {total})')
    print(f'  {detail}')

print()
print('=' * 78)
print('TONG HOP TOAN BO')
print('=' * 78)
for ext, count in overall.most_common():
    print(f'  {ext:<14} {count}')
print(f'\nTong file: {sum(overall.values())} | so loai duoi: {len(overall)}')

# Cột original_name lưu tên gốc người dùng đặt — kiểm tra riêng vì nó phản ánh
# đúng những gì user thực sự upload (kể cả khi tên lưu bị đổi).
print()
print('=' * 78)
print('TEN GOC NGUOI DUNG UPLOAD (original_name / display_name)')
print('=' * 78)
name_counter = Counter()
for model in apps.get_models():
    names = [
        f.name for f in model._meta.concrete_fields
        if f.name in ('original_name', 'display_name', 'file_name')
    ]
    if not names:
        continue
    for row in model._default_manager.values_list(*names).iterator():
        for value in row:
            if not value:
                continue
            ext = PurePosixPath(str(value)).suffix.lower() or '(khong co)'
            name_counter[ext] += 1
for ext, count in name_counter.most_common():
    print(f'  {ext:<14} {count}')
