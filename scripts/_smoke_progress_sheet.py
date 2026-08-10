from decimal import Decimal

from django.contrib.auth import get_user_model

from san_xuat.hub_models import SxProductionOrder, SxProductionOrderLine
from san_xuat.services.order_progress_sheet import build_progress_sheet, record_progress_qty

mo = (
    SxProductionOrder.objects.filter(
        is_demo=False,
        status__in=['released', 'in_progress', 'done'],
    )
    .order_by('-id')
    .first()
)
print('mo', getattr(mo, 'pk', None), getattr(mo, 'code', None), getattr(mo, 'status', None))
if not mo:
    raise SystemExit(0)

n_lines = SxProductionOrderLine.objects.filter(production_order=mo).count()
print('lines', n_lines)
sheet = build_progress_sheet(mo)
print('sizes', [(s.size_label, float(s.qty)) for s in sheet.sizes[:6]])
u = get_user_model().objects.filter(is_superuser=True).first()
size = sheet.sizes[0].size_label
st = record_progress_qty(
    mo_id=mo.pk,
    process_key='inep_la_co',
    size_label=size,
    qty=Decimal('1'),
    user=u,
)
print('ok', st.code, st.process_name, st.team_label, st.size_label, st.qty_good)
sheet2 = build_progress_sheet(mo)
cell = sheet2.matrix.get(size, {}).get('inep_la_co')
print('cell_done', cell.done if cell else None, 'remain', cell.remaining if cell else None)
