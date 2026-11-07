import os
from san_xuat.hub_models import SxRouteSheet, SxSalesOrder, SxSalesOrderPlanStep

REFRESH = os.environ.get('REFRESH') == '1'


def walk(node, out):
    if isinstance(node, dict):
        if 'team_label' in node and 'slug' in node and 'label' in node:
            out.append((node.get('slug'), node.get('label'), node.get('team_label')))
        for v in node.values():
            walk(v, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, out)


ids = sorted(set(
    SxSalesOrderPlanStep.objects.exclude(work_center__code__startswith='HRD-')
    .filter(work_center__isnull=False, sales_order__is_demo=False)
    .exclude(sales_order__plan_status__in=[SxSalesOrder.PLAN_DONE, SxSalesOrder.PLAN_CANCELLED])
    .values_list('sales_order_id', flat=True)
))
print('orders with KHSX team outside HR departments:', len(ids))


def shown():
    out = {}
    for sheet in SxRouteSheet.objects.filter(sales_order_id__in=ids).select_related('sales_order'):
        rows = []
        walk(sheet.payload, rows)
        out[sheet.sales_order_id] = (sheet.sales_order.code, sorted({r for r in rows if r[0] == 'd25'}))
    return out


before = shown()
if REFRESH:
    from san_xuat.services.route_sheet import refresh_route_sheets
    refresh_route_sheets(ids)
    after = shown()
    changed = 0
    for oid in ids:
        b, a = before.get(oid), after.get(oid)
        if b != a:
            changed += 1
            print('CHANGED', oid, b[0] if b else '', '|', b[1] if b else '-', '=>', a[1] if a else '-')
    print('changed orders:', changed)
else:
    bad = [(oid, v) for oid, v in before.items() if any(r[2] == r[1] for r in v[1])]
    print('rows where team == department (d25):', len(bad))
    for oid, v in bad:
        print('  ', oid, v)
