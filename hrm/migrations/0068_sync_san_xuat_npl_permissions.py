"""Đồng bộ menu hub SX + cấp Kho NPL cho nhóm quyền liên quan sản xuất.

- Bổ sung mọi key submenu ``san_xuat`` / ``kho_npl`` còn thiếu (nhóm đã có menus).
- Nhóm SX / KHSX / ĐBCL: materialize menus san_xuat + đảm bảo ``kho_npl`` (menu
  lồng dưới Sản xuất trên sidebar vẫn cần quyền module kho_npl).
"""

from django.db import migrations

SAN_XUAT_MENU_KEYS = (
    'overview',
    'orders',
    'plan',
    'plan_overall',
    'plan_detail',
    'plan_npl',
    'npl_pr',
    'purchase_order',
    'dispatch',
    'mo',
    'disassembly',
    'schedule',
    'material_issue_req',
    'prod_stats',
    'fg_receipt_req',
    'npl_surplus',
    'wip_handover',
    'wip_return',
    'handover_status',
    'qc',
    'qc_request',
    'qc_sheet',
    'qc_criteria',
    'qc_criteria_group',
    'qc_sampling',
    'qc_standard_set',
    'qc_defect',
    'qc_defect_group',
    'costing_hub',
    'costing_norm',
    'costing_so',
    'fg_stock',
    'fg_products',
    'fg_stock_list',
    'fg_purchases',
    'npl_stock',
    'process',
    'docs',
    'bom',
    'costing',
)

KHO_NPL_MENU_KEYS = (
    'overview',
    'materials',
    'material_stock',
    'stock_cards',
    'receipts',
    'issues',
    'transfers',
    'disposals',
    'adjustments',
    'stocktakes',
    'reports',
    'settings',
)

# Khớp tên/slug nhóm trên VPS: SX-*, KHSX*, ĐBCL*, …
_SX_RELATED_MARKERS = (
    'sx-',
    'sx ',
    'khsx',
    'đbcl',
    'dbcl',
    'sản xuất',
    'san xuat',
    'kế hoạch sản xuất',
    'ke hoach san xuat',
    'đảm bảo chất lượng',
    'dam bao chat luong',
)


def _flags(view=False, create=False, update=False, delete=False, export=False):
    if any((create, update, delete, export)):
        view = True
    return {
        'view': bool(view),
        'create': bool(create),
        'update': bool(update),
        'delete': bool(delete),
        'export': bool(export),
    }


def _template_from_entry(entry: dict) -> dict:
    return _flags(
        view=bool(entry.get('view')),
        create=bool(entry.get('create')),
        update=bool(entry.get('update')),
        delete=bool(entry.get('delete')),
        export=bool(entry.get('export')),
    )


def _is_managerish(name: str, slug: str) -> bool:
    text = f'{name} {slug}'.casefold()
    markers = ('tp', 'tt', 'trưởng', 'truong', 'manager', 'tổ trưởng', 'to truong')
    return any(m in text for m in markers)


def _is_sx_related(name: str, slug: str) -> bool:
    text = f'{name} {slug}'.casefold()
    return any(m in text for m in _SX_RELATED_MARKERS)


def _sync_menus(entry: dict, keys: tuple[str, ...], *, force_fill: bool, template: dict | None = None):
    """Trả (changed, new_entry)."""
    entry = dict(entry or {})
    menus = dict(entry.get('menus') or {})
    tpl = dict(template or _template_from_entry(entry))
    changed = False

    if force_fill and not menus:
        menus = {key: dict(tpl) for key in keys}
        changed = True
    else:
        for key in keys:
            if key not in menus:
                menus[key] = dict(tpl)
                changed = True

    if not changed:
        return False, entry
    entry['menus'] = menus
    # Gộp OR module flags từ menus
    for action in ('view', 'create', 'update', 'delete', 'export'):
        entry[action] = any(bool((menus.get(k) or {}).get(action)) for k in menus)
    return True, entry


def _ensure_kho_npl(perms: dict, *, manager: bool) -> tuple[bool, dict]:
    npl = dict(perms.get('kho_npl') or {})
    if manager:
        tpl = _flags(view=True, create=True, update=True, delete=True, export=True)
    else:
        tpl = _flags(view=True)
    changed = False
    if not npl.get('view'):
        npl = dict(tpl)
        changed = True
    menus = dict(npl.get('menus') or {})
    if not menus:
        npl['menus'] = {key: dict(tpl) for key in KHO_NPL_MENU_KEYS}
        changed = True
    else:
        for key in KHO_NPL_MENU_KEYS:
            if key not in menus:
                menus[key] = dict(tpl)
                changed = True
        npl['menus'] = menus
    for action in ('view', 'create', 'update', 'delete', 'export'):
        npl[action] = any(bool((npl.get('menus') or {}).get(k, {}).get(action)) for k in KHO_NPL_MENU_KEYS) or bool(npl.get(action))
    out = dict(perms)
    out['kho_npl'] = npl
    return changed, out


def forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        changed = False
        sx_related = _is_sx_related(group.name or '', group.slug or '')
        manager = _is_managerish(group.name or '', group.slug or '')

        sx = dict(perms.get('san_xuat') or {})
        if sx:
            if sx_related:
                tpl = (
                    _flags(view=True, create=True, update=True, delete=False, export=False)
                    if manager
                    else _flags(view=True)
                )
                # Materialize / sync mọi menu hub
                c, sx = _sync_menus(sx, SAN_XUAT_MENU_KEYS, force_fill=True, template=tpl)
            else:
                c, sx = _sync_menus(sx, SAN_XUAT_MENU_KEYS, force_fill=False)
            if c:
                perms['san_xuat'] = sx
                changed = True

        if sx_related:
            c2, perms = _ensure_kho_npl(perms, manager=manager)
            if c2:
                changed = True
        elif perms.get('kho_npl'):
            npl = dict(perms['kho_npl'])
            c3, npl = _sync_menus(npl, KHO_NPL_MENU_KEYS, force_fill=False)
            if c3:
                perms['kho_npl'] = npl
                changed = True

        if changed:
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])

    # Hiển thị menu phòng ban: nếu đã có Sản xuất thì thêm Kho NPL (menu lồng sidebar)
    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'san_xuat' in modules and 'kho_npl' not in modules:
            modules.append('kho_npl')
            perm.modules = modules
            perm.save(update_fields=['modules'])


def backward(apps, schema_editor):
    # Không gỡ quyền đã cấp — chỉ no-op an toàn.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0067_seed_san_xuat_fg_kv_menus'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
