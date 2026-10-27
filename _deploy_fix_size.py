import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from kho_npl.models import Material

qs = Material.objects.filter(size='', stock_domain='npl')
pattern = re.compile(r'^(.+?)\s+(S|M|L|XL|XXL|XXXL|XS|\d+/\d+|[A-Z]\d+)$', re.IGNORECASE)

updated_count = 0
errors = []

for m in qs:
    name_stripped = (m.name or '').strip()
    match = pattern.match(name_stripped)
    if match:
        new_name = match.group(1).strip()
        extracted_size = match.group(2).upper()
        try:
            m.name = new_name
            m.size = extracted_size
            m.save(update_fields=['name', 'size'])
            updated_count += 1
            print(f"  OK: ID={m.id}, code={m.code}, name={new_name!r}, size={extracted_size!r}")
        except Exception as e:
            errors.append(f"  LOI: ID={m.id}, code={m.code}: {e}")
            print(f"  LOI: ID={m.id}, code={m.code}: {e}")

print(f'\nDa cap nhat: {updated_count} NPL tren production.')
if errors:
    print(f'Loi: {len(errors)}')
    for err in errors:
        print(err)
else:
    print('Khong co loi.')