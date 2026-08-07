"""Gán demo Tải % trên tổ VPS: 80 / 100 / 150.

Chạy trên VPS:
  docker compose exec -T web python manage.py shell < scripts/_seed_work_center_load_pct.py
"""

from decimal import Decimal

from san_xuat.hub_models import SxWorkCenter

centers = list(
    SxWorkCenter.objects.filter(is_demo=False, is_active=True).order_by('code')
)
if not centers:
    print('No active work centers')
else:
    # Reset notes that look like our previous load demos, then assign pattern.
    for c in centers:
        if c.notes.startswith('Tải demo:'):
            c.notes = ''
            c.save(update_fields=['notes'])

    # Prefer HRD-* codes if present; else first N active centers.
    hrd = [c for c in centers if (c.code or '').upper().startswith('HRD')]
    pool = hrd if len(hrd) >= 3 else centers

    short = pool[0]
    ot = pool[-1]
    normal = [c for c in pool if c.pk not in (short.pk, ot.pk)]

    short.efficiency_pct = Decimal('80')
    short.notes = 'Tải demo: 80% — thiếu người'
    short.save(update_fields=['efficiency_pct', 'notes'])
    print(f'{short.code}: 80%')

    for c in normal:
        c.efficiency_pct = Decimal('100')
        c.notes = 'Tải demo: 100% — bình thường'
        c.save(update_fields=['efficiency_pct', 'notes'])
        print(f'{c.code}: 100%')

    if ot.pk != short.pk:
        ot.efficiency_pct = Decimal('150')
        ot.notes = 'Tải demo: 150% — tăng ca'
        ot.save(update_fields=['efficiency_pct', 'notes'])
        print(f'{ot.code}: 150%')

    print(f'Done. Updated {len(pool)} centers in pool (total active {len(centers)}).')
