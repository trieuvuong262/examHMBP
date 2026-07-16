"""Cầu nối một chiều Portal kho_npl → Odoo Inventory.

Khóa idempotent: Material.code == product.product.default_code

Giai đoạn:
  1. reconcile_materials — chỉ đọc
  2. ensure_npl_category_tree / ensure_npl_warehouse — master
  3. push_materials / push_npl_stock — ghi Odoo (--apply)

Đồng bộ MỘT CHIỀU: Portal kho_npl là nguồn sự thật.
Root category Odoo: «Kho NPL» (tách biệt «KiotViet»).
Warehouse code cố định: NPL (Odoo giới hạn ~5 ký tự).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from audit.services.odoo_sync import _execute, odoo_configured
from kho_npl.choices import WAREHOUSE_SCRAP_CODE
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockBalance,
    Supplier,
    Unit,
    WarehouseLocation,
)
from kho_npl.services.batches import material_avg_price
from kiotviet.odoo_bridge import (
    _safe_apply_inventory,
    fetch_odoo_products_by_code,
    odoo_ready,
)

logger = logging.getLogger(__name__)

NPL_CATEGORY_ROOT = 'Kho NPL'
NPL_WAREHOUSE_CODE = 'NPL'  # Odoo giới hạn code kho ~5 ký tự
NPL_WAREHOUSE_NAME = 'Kho Nguyên Phụ Liệu'

_ODOO_READ_BATCH = 400
_PRODUCT_CREATE_BATCH = 50
_STOCK_APPLY_BATCH = 500
_ODOO_FIELDS = ['id', 'default_code', 'name', 'list_price', 'standard_price', 'active', 'type']

# Portal Unit.code (slug) → Odoo uom search name / xml-ish hint
# Thiếu map → Units.
NPL_UOM_MAP: dict[str, str] = {
    'met': 'm',
    'm': 'm',
    'tm-ms': 'm',
    'tm-ms2': 'm',
    'tm-ms3': 'm',
    'tm-ms4': 'm',
    'kg': 'kg',
    'cai': 'Units',
    'bo': 'Units',
    'cuon': 'Units',
    'bao': 'Units',
    'goi': 'Units',
    'hop': 'Units',
    'to': 'Units',
    'can': 'Units',
}

# Cache process-local
_uom_cache: dict[str, int] = {}


class NplOdooBridgeError(Exception):
    pass


def odoo_npl_ready() -> bool:
    return odoo_ready() and odoo_configured()


def _norm_code(value) -> str:
    return (str(value).strip() if value else '')


def _to_float(value) -> float:
    if value is None or value == '':
        return 0.0
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def _m2o_id(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


# ------------------------------- UoM ---------------------------------------


def resolve_uom_id(unit: Unit | None, *, dry_run: bool = False) -> int | None:
    """Map Portal Unit → Odoo uom.uom id. Cache theo unit.code."""
    if unit is None:
        key = '__units__'
        search_name = 'Units'
    else:
        key = (unit.code or '').strip().lower()
        search_name = NPL_UOM_MAP.get(key, 'Units')

    if key in _uom_cache:
        return _uom_cache[key]

    if dry_run:
        return None

    # Ưu tiên name exact, rồi name ilike
    rows = _execute(
        'uom.uom', 'search_read',
        [['name', '=', search_name]],
        fields=['id', 'name'],
        limit=1,
    ) or []
    if not rows and search_name != 'Units':
        rows = _execute(
            'uom.uom', 'search_read',
            [['name', 'ilike', search_name]],
            fields=['id', 'name'],
            limit=1,
        ) or []
    if not rows:
        rows = _execute(
            'uom.uom', 'search_read',
            [['name', '=', 'Units']],
            fields=['id', 'name'],
            limit=1,
        ) or []
    if not rows:
        raise NplOdooBridgeError(f'Không tìm thấy UoM Odoo cho «{search_name}».')

    uid = rows[0]['id']
    _uom_cache[key] = uid
    if unit is not None and search_name == 'Units' and key not in NPL_UOM_MAP:
        logger.info('NPL UoM fallback Units cho unit.code=%s', unit.code)
    return uid


def map_uom_search_name(unit_code: str) -> str:
    """Helper testable: Portal unit code → Odoo search name."""
    return NPL_UOM_MAP.get((unit_code or '').strip().lower(), 'Units')


# ------------------------------- RECONCILE ---------------------------------


@dataclass
class NplReconResult:
    materials_total: int = 0
    matched: list = field(default_factory=list)
    missing_in_odoo: list = field(default_factory=list)
    name_mismatch: list = field(default_factory=list)
    price_mismatch: list = field(default_factory=list)
    duplicate_in_portal: list = field(default_factory=list)
    duplicate_in_odoo: list = field(default_factory=list)
    no_code: list = field(default_factory=list)
    conflict_demo_or_kv: list = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            'materials_total': self.materials_total,
            'matched': len(self.matched),
            'missing_in_odoo': len(self.missing_in_odoo),
            'name_mismatch': len(self.name_mismatch),
            'price_mismatch': len(self.price_mismatch),
            'duplicate_in_portal': len(self.duplicate_in_portal),
            'duplicate_in_odoo': len(self.duplicate_in_odoo),
            'no_code': len(self.no_code),
            'conflict_demo_or_kv': len(self.conflict_demo_or_kv),
        }


def reconcile_materials(*, limit: int | None = None) -> NplReconResult:
    """So khớp Material ↔ Odoo theo code=default_code. Chỉ đọc."""
    result = NplReconResult()
    qs = Material.objects.filter(is_active=True).select_related('unit', 'category').order_by('code')
    if limit:
        qs = qs[:limit]
    materials = list(qs)
    result.materials_total = len(materials)

    codes: list[str] = []
    seen: set[str] = set()
    for mat in materials:
        code = _norm_code(mat.code)
        if not code:
            result.no_code.append({'id': mat.pk, 'name': mat.name})
            continue
        if code in seen:
            result.duplicate_in_portal.append({'code': code, 'id': mat.pk})
            continue
        seen.add(code)
        codes.append(code)
        if code.upper().startswith('JP-DEMO'):
            result.conflict_demo_or_kv.append({'code': code, 'reason': 'JP-DEMO prefix'})

    existing = fetch_odoo_products_by_code(codes)
    for code in codes:
        recs = existing.get(code) or []
        if len(recs) > 1:
            result.duplicate_in_odoo.append({'code': code, 'count': len(recs)})
        if not recs:
            result.missing_in_odoo.append({'code': code})
            continue
        odoo = recs[0]
        mat = next(m for m in materials if _norm_code(m.code) == code)
        result.matched.append({'code': code, 'odoo_id': odoo['id']})
        odoo_name = (odoo.get('name') or '').strip()
        if odoo_name and odoo_name.upper() != (mat.name or '').strip().upper():
            result.name_mismatch.append({
                'code': code,
                'portal': mat.name,
                'odoo': odoo_name,
            })
        portal_price = float(material_avg_price(mat))
        odoo_price = _to_float(odoo.get('standard_price'))
        if portal_price > 0 and abs(portal_price - odoo_price) > 0.01:
            result.price_mismatch.append({
                'code': code,
                'portal': portal_price,
                'odoo': odoo_price,
            })
    return result


# ------------------------------- CATEGORY ----------------------------------


def _load_category_index() -> dict:
    records = _execute(
        'product.category', 'search_read', [],
        fields=['id', 'name', 'parent_id'],
    ) or []
    index = {}
    for rec in records:
        parent = rec.get('parent_id')
        pid = parent[0] if isinstance(parent, (list, tuple)) else 0
        index[(pid or 0, (rec.get('name') or '').strip().lower())] = rec['id']
    return index


def ensure_npl_category_tree(*, dry_run: bool = False) -> dict:
    """Tạo root «Kho NPL» + 1 cấp theo MaterialCategory.name."""
    index = _load_category_index()
    created: list[str] = []

    def _ensure(name: str, parent_id) -> int | None:
        key = (parent_id or 0, name.strip().lower())
        if key in index:
            return index[key]
        if dry_run:
            created.append(name if not parent_id else f'.../{name}')
            index[key] = None
            return None
        vals = {'name': name}
        if parent_id:
            vals['parent_id'] = parent_id
        new_id = _execute('product.category', 'create', vals)
        index[key] = new_id
        created.append(name if not parent_id else f'.../{name}')
        return new_id

    root_id = _ensure(NPL_CATEGORY_ROOT, None)
    cat_map: dict[int, int | None] = {}  # MaterialCategory.pk -> odoo categ id
    for cat in MaterialCategory.objects.filter(is_active=True).order_by('sort_order', 'name'):
        name = (cat.name or cat.code or '').strip() or cat.code
        cat_map[cat.pk] = _ensure(name, root_id)
    return {'root_id': root_id, 'cat_map': cat_map, 'created': created}


# ------------------------------- WAREHOUSE / LOCATION ----------------------


def _find_scrap_location_id(stock_location_id) -> int | None:
    """Odoo 18: stock.warehouse không còn scrap_loc_id — tìm location usage=inventory."""
    if not stock_location_id:
        return None
    # Ưu tiên scrap dưới cùng parent view của lot_stock
    stock = _execute(
        'stock.location', 'read', [stock_location_id],
        fields=['location_id'],
    ) or []
    parent_id = _m2o_id(stock[0].get('location_id')) if stock else None
    domain = [['usage', '=', 'inventory']]
    if parent_id:
        domain.append(['location_id', 'child_of', parent_id])
    rows = _execute(
        'stock.location', 'search_read', domain,
        fields=['id', 'complete_name'],
        limit=1,
    ) or []
    if rows:
        return rows[0]['id']
    rows = _execute(
        'stock.location', 'search_read',
        [['usage', '=', 'inventory']],
        fields=['id'],
        limit=1,
    ) or []
    return rows[0]['id'] if rows else None


def ensure_npl_warehouse(*, dry_run: bool = False) -> dict:
    """Tạo/khớp warehouse NPL. Trả warehouse_id, stock_location_id, scrap_location_id.

    Odoo giới hạn ``code`` ~5 ký tự — dùng ``NPL``. Khớp thêm theo tên nếu
    lần deploy cũ tạo code bị cắt (vd. KHO-N).
    """
    existing = _execute(
        'stock.warehouse', 'search_read',
        ['|', ['code', '=', NPL_WAREHOUSE_CODE], ['name', '=', NPL_WAREHOUSE_NAME]],
        fields=['id', 'name', 'code', 'lot_stock_id'],
        limit=5,
    ) or []
    # Ưu tiên đúng code NPL, rồi đúng tên
    wh = None
    for row in existing:
        if (row.get('code') or '') == NPL_WAREHOUSE_CODE:
            wh = row
            break
    if wh is None and existing:
        wh = existing[0]

    if wh:
        stock_loc = _m2o_id(wh.get('lot_stock_id'))
        # Chuẩn hóa code nếu bị cắt từ deploy cũ
        if not dry_run and (wh.get('code') or '') != NPL_WAREHOUSE_CODE:
            try:
                _execute('stock.warehouse', 'write', [wh['id']], {'code': NPL_WAREHOUSE_CODE})
            except Exception as exc:  # noqa: BLE001
                logger.warning('Không đổi code warehouse về NPL: %s', exc)
        return {
            'warehouse_id': wh['id'],
            'stock_location_id': stock_loc,
            'scrap_location_id': _find_scrap_location_id(stock_loc) if not dry_run else None,
            'created': False,
            'name': wh.get('name') or NPL_WAREHOUSE_NAME,
        }

    if dry_run:
        return {
            'warehouse_id': None,
            'stock_location_id': None,
            'scrap_location_id': None,
            'created': True,
            'name': NPL_WAREHOUSE_NAME,
        }

    wid = _execute('stock.warehouse', 'create', {
        'name': NPL_WAREHOUSE_NAME,
        'code': NPL_WAREHOUSE_CODE,
    })
    wh = _execute(
        'stock.warehouse', 'read', [wid],
        fields=['id', 'name', 'lot_stock_id'],
    )[0]
    stock_loc = _m2o_id(wh.get('lot_stock_id'))
    return {
        'warehouse_id': wid,
        'stock_location_id': stock_loc,
        'scrap_location_id': _find_scrap_location_id(stock_loc),
        'created': True,
        'name': wh.get('name') or NPL_WAREHOUSE_NAME,
    }


def ensure_npl_locations(stock_location_id, scrap_location_id=None, *, dry_run: bool = False) -> dict:
    """Map WarehouseLocation.code → stock.location dưới stock (hoặc scrap cho HUY).

    Location name = «{code} — {name}» để dễ nhận; barcode = code (nếu field cho phép).
    """
    loc_map: dict[int, int | None] = {}  # portal location pk -> odoo location id
    created: list[str] = []
    reused: list[str] = []

    if not stock_location_id and not dry_run:
        raise NplOdooBridgeError('Thiếu stock_location_id của warehouse NPL.')

    portal_locs = list(WarehouseLocation.objects.filter(is_active=True).order_by('code'))
    if dry_run:
        for loc in portal_locs:
            loc_map[loc.pk] = None
            created.append(loc.code)
        return {'map': loc_map, 'created': created, 'reused': reused}

    # Index existing children under stock (and scrap parent)
    parent_ids = [p for p in [stock_location_id, scrap_location_id] if p]
    children = _execute(
        'stock.location', 'search_read',
        [['location_id', 'in', parent_ids]],
        fields=['id', 'name', 'barcode', 'location_id'],
    ) or []
    by_barcode = {}
    by_name_prefix = {}
    for ch in children:
        bc = _norm_code(ch.get('barcode'))
        if bc:
            by_barcode[bc] = ch['id']
        name = (ch.get('name') or '').strip()
        if name:
            by_name_prefix[name.lower()] = ch['id']
            token = name.split('—')[0].strip().lower()
            by_name_prefix[token] = ch['id']

    for loc in portal_locs:
        code = _norm_code(loc.code)
        parent = scrap_location_id if code == WAREHOUSE_SCRAP_CODE and scrap_location_id else stock_location_id
        display = f'{code} — {loc.display_label()}'
        existing_id = by_barcode.get(code) or by_name_prefix.get(display.lower()) or by_name_prefix.get(code.lower())
        if existing_id:
            loc_map[loc.pk] = existing_id
            reused.append(code)
            continue

        vals = {
            'name': display,
            'location_id': parent,
            'usage': 'internal',
            'barcode': code,
        }
        try:
            new_id = _execute('stock.location', 'create', vals)
        except Exception:
            # barcode có thể unique conflict / field readonly — thử không barcode
            vals.pop('barcode', None)
            new_id = _execute('stock.location', 'create', vals)
        loc_map[loc.pk] = new_id
        created.append(code)
        by_barcode[code] = new_id
        by_name_prefix[display.lower()] = new_id

    return {'map': loc_map, 'created': created, 'reused': reused}


# ------------------------------- SUPPLIERS ---------------------------------


def _partner_vals_from_supplier(sup: Supplier) -> dict:
    code = _norm_code(sup.code)
    return {
        'name': (sup.name or code or '').strip() or code,
        'ref': code,
        'phone': (sup.phone or '').strip(),
        'comment': (sup.notes or '').strip(),
        'supplier_rank': 1,
        'customer_rank': 0,
        'company_type': 'company',
        'active': bool(sup.is_active),
    }


def ensure_npl_suppliers(*, dry_run: bool = False) -> dict:
    """Đẩy Supplier Portal → res.partner. Khóa: partner.ref == Supplier.code."""
    suppliers = list(Supplier.objects.exclude(code='').order_by('code'))
    created: list[str] = []
    updated: list[str] = []
    partner_map: dict[int, int | None] = {}

    if dry_run:
        for sup in suppliers:
            partner_map[sup.pk] = None
            created.append(_norm_code(sup.code))
        return {'map': partner_map, 'created': created, 'updated': updated}

    codes = [_norm_code(s.code) for s in suppliers if _norm_code(s.code)]
    by_ref: dict[str, int] = {}
    for i in range(0, len(codes), _ODOO_READ_BATCH):
        chunk = codes[i:i + _ODOO_READ_BATCH]
        rows = _execute(
            'res.partner', 'search_read',
            [['ref', 'in', chunk]],
            fields=['id', 'ref'],
        ) or []
        for row in rows:
            ref = _norm_code(row.get('ref'))
            if ref:
                by_ref[ref] = row['id']

    for sup in suppliers:
        code = _norm_code(sup.code)
        if not code:
            continue
        vals = _partner_vals_from_supplier(sup)
        existing_id = by_ref.get(code)
        if existing_id:
            try:
                _execute('res.partner', 'write', [existing_id], vals)
                partner_map[sup.pk] = existing_id
                updated.append(code)
            except Exception as exc:  # noqa: BLE001
                logger.warning('NPL partner update %s failed: %s', code, exc)
                partner_map[sup.pk] = existing_id
            continue
        try:
            new_id = _execute('res.partner', 'create', vals)
            partner_map[sup.pk] = new_id
            by_ref[code] = new_id
            created.append(code)
        except Exception as exc:  # noqa: BLE001
            logger.warning('NPL partner create %s failed: %s', code, exc)
            partner_map[sup.pk] = None

    return {'map': partner_map, 'created': created, 'updated': updated}


def link_material_vendors(
    codes: set[str],
    partner_map: dict[int, int | None],
    result: 'NplPushResult',
) -> None:
    """Gắn product.supplierinfo (seller) cho NPL có NCC chính trên Portal."""
    if not codes or not partner_map:
        return

    materials = list(
        Material.objects.filter(code__in=codes, supplier_id__isnull=False)
        .exclude(code='')
        .select_related('supplier'),
    )
    if not materials:
        return

    variants = fetch_odoo_products_by_code({_norm_code(m.code) for m in materials})
    for mat in materials:
        code = _norm_code(mat.code)
        partner_id = partner_map.get(mat.supplier_id)
        odoo_records = variants.get(code)
        if not partner_id or not odoo_records:
            continue
        try:
            tmpl = _execute(
                'product.product', 'read', [odoo_records[0]['id']],
                fields=['product_tmpl_id'],
            )[0]['product_tmpl_id']
            tmpl_id = _m2o_id(tmpl)
            existing = _execute(
                'product.supplierinfo', 'search_read',
                [['product_tmpl_id', '=', tmpl_id], ['partner_id', '=', partner_id]],
                fields=['id'],
                limit=1,
            ) or []
            price = float(material_avg_price(mat) or mat.base_price or 0)
            if existing:
                _execute(
                    'product.supplierinfo', 'write', [existing[0]['id']],
                    {'price': price},
                )
            else:
                _execute('product.supplierinfo', 'create', {
                    'partner_id': partner_id,
                    'product_tmpl_id': tmpl_id,
                    'price': price,
                    'delay': 1,
                    'min_qty': 0.0,
                })
            result.vendors_linked += 1
        except Exception as exc:  # noqa: BLE001
            result.materials_failed.append({
                'code': code,
                'error': f'vendor: {str(exc)[:180]}',
            })


# ------------------------------- PRODUCTS ----------------------------------


def build_material_vals(material: Material, categ_id, uom_id) -> dict:
    """Pure-ish vals builder (uom_id có thể None ở dry-run)."""
    cost = material_avg_price(material)
    vals = {
        'name': (material.name or material.code or '').strip() or material.code,
        'default_code': _norm_code(material.code),
        'type': 'consu',
        'is_storable': True,
        'sale_ok': False,
        'purchase_ok': True,
        'list_price': 0.0,
        'standard_price': float(cost) if cost else 0.0,
        'active': bool(material.is_active),
    }
    if categ_id:
        vals['categ_id'] = categ_id
    if uom_id:
        vals['uom_id'] = uom_id
        vals['uom_po_id'] = uom_id
    return vals


@dataclass
class NplPushResult:
    dry_run: bool = True
    categories_created: list = field(default_factory=list)
    warehouse_created: bool = False
    locations_created: list = field(default_factory=list)
    suppliers_created: list = field(default_factory=list)
    suppliers_updated: list = field(default_factory=list)
    vendors_linked: int = 0
    materials_total: int = 0
    materials_created: int = 0
    materials_updated: int = 0
    materials_skipped: int = 0
    materials_failed: list = field(default_factory=list)
    stock_applied: int = 0
    stock_failed: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            'dry_run': self.dry_run,
            'categories_created': len(self.categories_created),
            'warehouse_created': self.warehouse_created,
            'locations_created': len(self.locations_created),
            'suppliers_created': len(self.suppliers_created),
            'suppliers_updated': len(self.suppliers_updated),
            'vendors_linked': self.vendors_linked,
            'materials_total': self.materials_total,
            'materials_created': self.materials_created,
            'materials_updated': self.materials_updated,
            'materials_skipped': self.materials_skipped,
            'materials_failed': len(self.materials_failed),
            'stock_applied': self.stock_applied,
            'stock_failed': len(self.stock_failed),
        }


def _create_products_batch(vals_list: list[dict], result: NplPushResult) -> None:
    if not vals_list:
        return
    try:
        ids = _execute('product.template', 'create', vals_list)
        result.materials_created += len(ids if isinstance(ids, list) else [ids])
        return
    except Exception:
        pass
    for vals in vals_list:
        try:
            _execute('product.template', 'create', vals)
            result.materials_created += 1
        except Exception as exc:  # noqa: BLE001
            result.materials_failed.append({'code': vals.get('default_code'), 'error': str(exc)[:200]})


def push_materials(
    *,
    dry_run: bool = True,
    limit: int | None = None,
    codes: set[str] | None = None,
    with_stock: bool = True,
    update_existing: bool = True,
    progress=None,
) -> NplPushResult:
    """Đẩy danh mục + NPL (+ tồn) Portal → Odoo."""
    result = NplPushResult(dry_run=dry_run)

    def _log(msg, pct=None):
        if progress:
            progress(msg, pct)

    _log('Chuẩn bị danh mục Kho NPL...', 3)
    cat = ensure_npl_category_tree(dry_run=dry_run)
    result.categories_created = cat['created']
    cat_map = cat['cat_map']
    root_id = cat['root_id']

    _log('Chuẩn bị warehouse NPL...', 8)
    wh = ensure_npl_warehouse(dry_run=dry_run)
    result.warehouse_created = bool(wh.get('created'))

    _log('Chuẩn bị vị trí kho...', 12)
    locs = ensure_npl_locations(
        wh.get('stock_location_id'),
        wh.get('scrap_location_id'),
        dry_run=dry_run,
    )
    result.locations_created = locs['created']
    loc_map = locs['map']

    _log('Chuẩn bị nhà cung cấp...', 15)
    suppliers = ensure_npl_suppliers(dry_run=dry_run)
    result.suppliers_created = suppliers['created']
    result.suppliers_updated = suppliers['updated']
    partner_map = suppliers['map']

    qs = (
        Material.objects.filter(is_active=True)
        .exclude(code='')
        .select_related('unit', 'category', 'supplier')
        .order_by('code')
    )
    if codes:
        normed = {_norm_code(c) for c in codes if _norm_code(c)}
        qs = qs.filter(code__in=normed)
    if limit:
        qs = qs[:limit]
    materials = list(qs)
    result.materials_total = len(materials)

    seen: set[str] = set()
    unique: list[Material] = []
    for mat in materials:
        code = _norm_code(mat.code)
        if code in seen:
            continue
        seen.add(code)
        unique.append(mat)

    existing = fetch_odoo_products_by_code(seen) if (not dry_run or update_existing) else {}
    if dry_run and not existing:
        # Vẫn đọc để báo update vs create chính xác hơn
        existing = fetch_odoo_products_by_code(seen)

    to_create: list[dict] = []
    for mat in unique:
        code = _norm_code(mat.code)
        categ_id = cat_map.get(mat.category_id) or root_id
        uom_id = resolve_uom_id(mat.unit, dry_run=dry_run)
        odoo_records = existing.get(code)

        if odoo_records:
            if not update_existing:
                result.materials_skipped += 1
                continue
            if dry_run:
                result.materials_updated += 1
                continue
            vals = build_material_vals(mat, categ_id, uom_id)
            vals.pop('default_code', None)
            try:
                tmpl = _execute(
                    'product.product', 'read', [odoo_records[0]['id']],
                    fields=['product_tmpl_id'],
                )[0]['product_tmpl_id']
                tmpl_id = _m2o_id(tmpl)
                _execute('product.template', 'write', [tmpl_id], vals)
                result.materials_updated += 1
            except Exception as exc:  # noqa: BLE001
                result.materials_failed.append({'code': code, 'error': str(exc)[:200]})
            continue

        if dry_run:
            result.materials_created += 1
            continue

        to_create.append(build_material_vals(mat, categ_id, uom_id))
        if len(to_create) >= _PRODUCT_CREATE_BATCH:
            _create_products_batch(to_create, result)
            to_create = []

    if to_create:
        _create_products_batch(to_create, result)

    _log(
        f'Xong NPL: tạo {result.materials_created}, cập nhật {result.materials_updated}.',
        78,
    )

    if not dry_run:
        _log('Gắn vendor (NCC chính) lên product...', 82)
        link_material_vendors(seen, partner_map, result)
    else:
        with_vendor = sum(1 for m in unique if m.supplier_id)
        result.vendors_linked = with_vendor

    if with_stock and not dry_run:
        _log('Đang set tồn NPL...', 85)
        push_npl_stock(seen, loc_map, result, progress=progress)
    elif with_stock and dry_run:
        _log('(dry-run) Bỏ qua ghi tồn kho.', 95)

    return result


def push_npl_stock(
    codes: set[str],
    loc_map: dict[int, int | None],
    result: NplPushResult,
    *,
    progress=None,
) -> None:
    """Set tồn từ StockBalance → stock.quant (inventory mode)."""
    valid_locs = {pk: lid for pk, lid in loc_map.items() if lid}
    if not valid_locs:
        return

    variants = fetch_odoo_products_by_code(codes)
    code_to_pid = {c: recs[0]['id'] for c, recs in variants.items() if recs}

    mat_ids = list(
        Material.objects.filter(code__in=codes).values_list('id', 'code'),
    )
    id_to_code = {mid: _norm_code(code) for mid, code in mat_ids}

    balances = list(
        StockBalance.objects.filter(
            material_id__in=list(id_to_code.keys()),
            location_id__in=list(valid_locs.keys()),
        ).values('material_id', 'location_id', 'quantity')
    )

    targets: dict[tuple[int, int], float] = {}
    for row in balances:
        code = id_to_code.get(row['material_id'])
        pid = code_to_pid.get(code)
        loc = valid_locs.get(row['location_id'])
        if not pid or not loc:
            continue
        qty = float(row['quantity'] or 0)
        if qty < 0:
            qty = 0.0
        targets[(pid, loc)] = qty

    if not targets:
        return

    total = max(1, len(targets))
    if progress:
        progress(f'Chuẩn bị ghi {len(targets)} dòng tồn NPL...', 86)

    pids = list({pid for pid, _ in targets})
    loc_ids = list({loc for _, loc in targets})
    existing_quants: dict[tuple[int, int], int] = {}
    for i in range(0, len(pids), _ODOO_READ_BATCH):
        chunk = pids[i:i + _ODOO_READ_BATCH]
        rows = _execute(
            'stock.quant', 'search_read',
            [['product_id', 'in', chunk], ['location_id', 'in', loc_ids]],
            fields=['id', 'product_id', 'location_id'],
            context={'inventory_mode': True},
        ) or []
        for q in rows:
            p = _m2o_id(q['product_id'])
            l = _m2o_id(q['location_id'])
            existing_quants[(p, l)] = q['id']

    quant_ids: list[int] = []
    to_create: list[dict] = []
    for (pid, loc), qty in targets.items():
        qid = existing_quants.get((pid, loc))
        if qid:
            try:
                _execute(
                    'stock.quant', 'write', [qid],
                    {'inventory_quantity': qty},
                    context={'inventory_mode': True},
                )
                quant_ids.append(qid)
            except Exception as exc:  # noqa: BLE001
                result.stock_failed.append({'pid': pid, 'loc': loc, 'error': str(exc)[:150]})
        else:
            to_create.append({
                'product_id': pid,
                'location_id': loc,
                'inventory_quantity': qty,
            })

    for i in range(0, len(to_create), _STOCK_APPLY_BATCH):
        batch = to_create[i:i + _STOCK_APPLY_BATCH]
        try:
            ids = _execute('stock.quant', 'create', batch, context={'inventory_mode': True})
            quant_ids.extend(ids if isinstance(ids, list) else [ids])
        except Exception:
            for vals in batch:
                try:
                    qid = _execute('stock.quant', 'create', vals, context={'inventory_mode': True})
                    quant_ids.append(qid)
                except Exception as exc:  # noqa: BLE001
                    result.stock_failed.append({
                        'pid': vals['product_id'],
                        'loc': vals['location_id'],
                        'error': str(exc)[:150],
                    })

    if progress:
        progress(f'Áp dụng tồn kho ({len(quant_ids)} dòng)...', 94)
    for i in range(0, len(quant_ids), _STOCK_APPLY_BATCH):
        batch = quant_ids[i:i + _STOCK_APPLY_BATCH]
        try:
            _safe_apply_inventory(batch)
            result.stock_applied += len(batch)
        except Exception as exc:  # noqa: BLE001
            result.stock_failed.append({'batch_start': i, 'error': str(exc)[:150]})
