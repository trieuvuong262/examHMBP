#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell -c "
from collections import Counter
from kho_npl.models import Material, MaterialCategory
rows = Material.objects.filter(is_active=True).select_related('category', 'category__parent')
no_parent = [m for m in rows if m.category_id and not m.category.parent_id]
print('active materials:', rows.count())
print('category has no parent (nhom cap 1 trong bang = —):', len(no_parent))
c = Counter(m.category.code for m in no_parent)
for code, n in c.most_common(15):
    cat = MaterialCategory.objects.get(code=code)
    print(f'  {code} ({cat.name}): {n}')
"
