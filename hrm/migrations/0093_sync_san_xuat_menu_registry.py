"""Đồng bộ menu Sản xuất: thêm `ie` + mọi key registry còn thiếu trong nhóm quyền."""

from django.db import migrations

# Nguồn kế thừa khi seed menu mới (ưu tiên trái → phải).
INHERIT_FROM = {
    'ie': ('bom', 'docs', 'capacity'),
    'capacity_load': ('capacity',),
    'stock_policy': ('plan_npl', 'plan_board', 'plan'),
    'restock': ('plan_npl', 'plan_board', 'plan'),
    'purchase_order': ('npl_pr', 'plan_npl', 'plan'),
    'plan_audit': ('plan_board', 'plan'),
    'disassembly': ('mo', 'dispatch'),
    'schedule': ('mo', 'dispatch'),
    'prod_stats': ('mo', 'dispatch'),
    'npl_surplus': ('material_issue_req', 'dispatch'),
    'wip_handover': ('handover_status', 'dispatch'),
    'wip_return': ('handover_status', 'dispatch'),
    'packing': ('mo', 'dispatch', 'fg_receipt_req'),
    'shop_floor': ('mo', 'dispatch', 'team_work'),
    'downtime': ('shop_floor', 'mo', 'dispatch'),
    'piece_rate': ('ops_report', 'shop_floor', 'mo'),
    'actual_cost': ('costing_hub', 'costing_so', 'costing_norm'),
    'team_work_goods': ('team_work', 'team_work_cat', 'dispatch'),
    'plan_route': ('plan_board', 'plan'),
    'plan_board': ('plan',),
    'order_create': ('orders',),
    'order_confirm': ('orders',),
}


def _flags_from(entry: dict) -> dict:
    return {
        'view': bool(entry.get('view')),
        'create': bool(entry.get('create') or entry.get('update')),
        'update': bool(entry.get('update')),
        'delete': bool(entry.get('delete')),
        'export': bool(entry.get('export')),
        'print': bool(entry.get('print')),
    }


def _resolve_template(menus: dict, key: str, sx: dict) -> dict:
    for src in INHERIT_FROM.get(key, ()):
        if src in menus and isinstance(menus[src], dict):
            return _flags_from(menus[src])
    # fallback: bất kỳ menu cùng module / quyền module
    for menu in menus.values():
        if isinstance(menu, dict) and menu.get('view'):
            return _flags_from(menu)
    return _flags_from(sx)


def _registry_keys():
    # Giữ list tĩnh trong migration (không import code app đang chạy).
    return (
        'overview', 'orders', 'order_create', 'order_confirm', 'products_nvl',
        'docs', 'bom', 'ie', 'capacity', 'capacity_load',
        'plan', 'plan_board', 'plan_route', 'plan_progress', 'plan_overall', 'plan_detail',
        'plan_npl', 'npl_pr', 'purchase_order', 'stock_policy', 'restock', 'plan_audit',
        'npl_stock',
        'dispatch', 'mo', 'disassembly', 'schedule', 'material_issue_req', 'prod_stats',
        'handover_status', 'fg_receipt_req', 'npl_surplus', 'wip_handover', 'wip_return',
        'subcontract', 'packing',
        'team_work', 'team_work_goods', 'team_work_cat', 'team_work_inep', 'team_work_theu',
        'team_work_may', 'team_work_ht', 'team_work_gh', 'work_assign',
        'shop_floor', 'downtime', 'piece_rate',
        'qc', 'qc_request', 'qc_sheet', 'ncr',
        'qc_criteria', 'qc_criteria_group', 'qc_sampling', 'qc_standard_set',
        'qc_defect', 'qc_defect_group',
        'fg_stock', 'fg_products', 'fg_stock_list', 'fg_purchases',
        'costing_hub', 'costing_norm', 'costing_so', 'actual_cost',
        'traceability', 'ops_report',
        'process', 'unified_catalog', 'staging',
        'general_settings',
    )


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    keys = _registry_keys()
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        if not sx:
            continue
        menus = dict(sx.get('menus') or {})
        if not menus:
            continue
        changed = False
        for key in keys:
            if key not in menus:
                menus[key] = _resolve_template(menus, key, sx)
                changed = True
        if changed:
            sx['menus'] = menus
            for action in ('view', 'create', 'update', 'delete', 'export', 'print'):
                sx[action] = any(bool((menus.get(k) or {}).get(action)) for k in menus) or bool(sx.get(action))
            perms['san_xuat'] = sx
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    # Không gỡ hàng loạt — chỉ gỡ `ie` nếu muốn rollback nhẹ.
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if 'ie' in menus:
            menus.pop('ie')
            sx['menus'] = menus
            perms['san_xuat'] = sx
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0092_seed_san_xuat_ie_menu'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
