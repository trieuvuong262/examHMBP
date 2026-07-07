"""Cầu nối một chiều KiotViet mirror → Odoo.

Giai đoạn 1 — ĐỐI CHIẾU (chỉ đọc): so khớp ``kv_product`` với Odoo theo khóa
    KvProduct.code  ==  Odoo product.product.default_code

Giai đoạn 2 — ĐẨY DỮ LIỆU (ghi Odoo, có --dry-run):
    - ensure_category_tree : tạo nhóm gốc 'KiotViet' + cây danh mục từ category_path
    - ensure_warehouses    : tạo/khớp kho Odoo theo chi nhánh KiotViet
    - push_products        : tạo/cập nhật product.template (default_code, giá, categ)
    - push_stock           : set tồn kho từng kho qua stock.quant (idempotent)

Đồng bộ MỘT CHIỀU: KiotViet là nguồn sự thật. Khóa idempotent là default_code
nên chạy lại nhiều lần không tạo trùng.
"""

from __future__ import annotations

import logging
import unicodedata
import xmlrpc.client
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from audit.services.odoo_sync import _execute, odoo_configured
from kiotviet.models import KvBranch, KvProduct, KvProductInventory
from kiotviet.sync_service import current_retailer

logger = logging.getLogger(__name__)

PRICE_TOLERANCE = Decimal('0.01')
_ODOO_READ_BATCH = 400
_ODOO_FIELDS = ['id', 'default_code', 'barcode', 'name', 'list_price', 'active', 'type']

KV_CATEGORY_ROOT = 'KiotViet'
_CATEGORY_SEPARATORS = ('>>', '>', '/', '\\')
_PRODUCT_CREATE_BATCH = 50


def odoo_ready() -> bool:
    """True khi Odoo XML-RPC đã cấu hình đủ (ODOO_URL/DB/API_USER/PASSWORD)."""
    return odoo_configured()


def _norm_code(value) -> str:
    return (str(value).strip() if value else '')


def _to_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def fetch_odoo_products_by_code(codes) -> dict[str, list[dict]]:
    """Đọc SP Odoo theo danh sách default_code. Chỉ đọc, gồm cả SP inactive.

    Trả về dict: code -> list[record]. Có thể >1 record nếu Odoo trùng mã.
    """
    result: dict[str, list[dict]] = {}
    unique_codes = [c for c in {_norm_code(c) for c in codes} if c]
    if not unique_codes:
        return result

    for i in range(0, len(unique_codes), _ODOO_READ_BATCH):
        chunk = unique_codes[i:i + _ODOO_READ_BATCH]
        records = _execute(
            'product.product',
            'search_read',
            [['default_code', 'in', chunk]],
            fields=_ODOO_FIELDS,
            context={'active_test': False},
        )
        for rec in records or []:
            key = _norm_code(rec.get('default_code'))
            if key:
                result.setdefault(key, []).append(rec)
    return result


@dataclass
class ReconResult:
    retailer: str = ''
    kv_total: int = 0
    odoo_matched_codes: int = 0
    matched: list = field(default_factory=list)
    missing_in_odoo: list = field(default_factory=list)
    price_mismatch: list = field(default_factory=list)
    name_mismatch: list = field(default_factory=list)
    duplicate_in_kv: list = field(default_factory=list)
    duplicate_in_odoo: list = field(default_factory=list)
    no_code: list = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            'kv_total': self.kv_total,
            'matched': len(self.matched),
            'missing_in_odoo': len(self.missing_in_odoo),
            'price_mismatch': len(self.price_mismatch),
            'name_mismatch': len(self.name_mismatch),
            'duplicate_in_kv': len(self.duplicate_in_kv),
            'duplicate_in_odoo': len(self.duplicate_in_odoo),
            'no_code': len(self.no_code),
        }


def _kv_products(retailer: str):
    qs = KvProduct.objects.filter(is_deleted=False)
    if retailer:
        qs = qs.filter(retailer=retailer)
    # Bỏ SP đã ngừng kinh doanh; giữ is_active True hoặc chưa xác định (None).
    return qs.exclude(is_active=False).order_by('code', 'kiotviet_id')


def reconcile_products(retailer: str | None = None) -> ReconResult:
    """So khớp kv_product ↔ Odoo theo code=default_code. Chỉ đọc."""
    retailer = retailer if retailer is not None else current_retailer()
    result = ReconResult(retailer=retailer)

    products = list(_kv_products(retailer))
    result.kv_total = len(products)
    if not products:
        return result

    # Gom theo mã để phát hiện trùng mã trong chính KiotViet.
    by_code: dict[str, list[KvProduct]] = {}
    for prod in products:
        code = _norm_code(prod.code)
        if not code:
            result.no_code.append({
                'kiotviet_id': prod.kiotviet_id,
                'name': prod.name,
                'bar_code': prod.bar_code,
            })
            continue
        by_code.setdefault(code, []).append(prod)

    odoo_by_code = fetch_odoo_products_by_code(by_code.keys())
    result.odoo_matched_codes = len(odoo_by_code)

    for code, kv_group in by_code.items():
        if len(kv_group) > 1:
            result.duplicate_in_kv.append({
                'code': code,
                'count': len(kv_group),
                'kiotviet_ids': [p.kiotviet_id for p in kv_group],
                'names': [p.name for p in kv_group],
            })

        kv = kv_group[0]
        odoo_records = odoo_by_code.get(code)

        if not odoo_records:
            result.missing_in_odoo.append({
                'code': code,
                'kiotviet_id': kv.kiotviet_id,
                'name': kv.name,
                'bar_code': kv.bar_code,
                'base_price': str(kv.base_price) if kv.base_price is not None else '',
                'category_path': kv.category_path,
            })
            continue

        if len(odoo_records) > 1:
            result.duplicate_in_odoo.append({
                'code': code,
                'count': len(odoo_records),
                'odoo_ids': [r.get('id') for r in odoo_records],
            })

        odoo = odoo_records[0]
        result.matched.append({
            'code': code,
            'kiotviet_id': kv.kiotviet_id,
            'odoo_id': odoo.get('id'),
            'kv_name': kv.name,
            'odoo_name': odoo.get('name'),
        })

        kv_price = _to_decimal(kv.base_price)
        odoo_price = _to_decimal(odoo.get('list_price'))
        if kv_price is not None and odoo_price is not None:
            if abs(kv_price - odoo_price) > PRICE_TOLERANCE:
                result.price_mismatch.append({
                    'code': code,
                    'kiotviet_id': kv.kiotviet_id,
                    'odoo_id': odoo.get('id'),
                    'kv_price': str(kv_price),
                    'odoo_price': str(odoo_price),
                })

        kv_name = (kv.name or '').strip()
        odoo_name = (odoo.get('name') or '').strip()
        if kv_name and odoo_name and kv_name.lower() != odoo_name.lower():
            result.name_mismatch.append({
                'code': code,
                'kiotviet_id': kv.kiotviet_id,
                'odoo_id': odoo.get('id'),
                'kv_name': kv_name,
                'odoo_name': odoo_name,
            })

    return result


# ---------------------------------------------------------------------------
# GIAI ĐOẠN 2 — ĐẨY DỮ LIỆU KiotViet → Odoo (một chiều, idempotent)
# ---------------------------------------------------------------------------


def _ascii_slug(text: str) -> str:
    """Bỏ dấu tiếng Việt, giữ chữ/số HOA — dùng sinh mã kho Odoo."""
    norm = unicodedata.normalize('NFKD', text or '')
    ascii_only = norm.encode('ascii', 'ignore').decode('ascii')
    return ''.join(ch for ch in ascii_only.upper() if ch.isalnum())


def _split_category_path(path: str) -> list[str]:
    raw = (path or '').strip()
    if not raw:
        return []
    for sep in _CATEGORY_SEPARATORS:
        if sep in raw:
            parts = raw.split(sep)
            break
    else:
        parts = [raw]
    return [p.strip() for p in parts if p.strip()]


# ------------------------------- KHO / WAREHOUSE ---------------------------


def _inventory_branches(retailer: str, branch_filter: set[int] | None) -> dict[int, str]:
    """Trả về {branch_kiotviet_id: branch_name} xuất hiện trong tồn kho."""
    qs = (
        KvProductInventory.objects
        .filter(retailer=retailer, is_deleted=False)
        .values('branch_kiotviet_id', 'branch_name')
        .distinct()
    )
    branches: dict[int, str] = {}
    kv_names = {
        b.kiotviet_id: (b.branch_name or '').strip()
        for b in KvBranch.objects.filter(retailer=retailer, is_deleted=False)
    }
    for row in qs:
        bid = row['branch_kiotviet_id']
        if branch_filter and bid not in branch_filter:
            continue
        name = kv_names.get(bid) or (row['branch_name'] or '').strip() or f'Chi nhánh {bid}'
        branches[bid] = name
    return branches


def _unique_warehouse_code(base: str, used: set[str]) -> str:
    base = (base or 'KV')[:5] or 'KV'
    if base not in used:
        used.add(base)
        return base
    for i in range(1, 100):
        suffix = str(i)
        cand = (base[:5 - len(suffix)] or 'K') + suffix
        if cand not in used:
            used.add(cand)
            return cand
    raise OdooBridgeError('Không sinh được mã kho Odoo duy nhất.')


class OdooBridgeError(Exception):
    pass


def _safe_apply_inventory(ids) -> None:
    """action_apply_inventory trả None → Odoo XML-RPC ném Fault 'cannot marshal None'
    dù thao tác đã áp dụng thành công server-side. Nuốt đúng lỗi vô hại này."""
    try:
        _execute('stock.quant', 'action_apply_inventory', ids, context={'inventory_mode': True})
    except xmlrpc.client.Fault as fault:
        if 'cannot marshal None' in str(fault):
            return
        raise


def ensure_warehouses(retailer: str, branch_filter=None, *, dry_run: bool = False) -> dict:
    """Tạo/khớp kho Odoo theo chi nhánh KiotViet (khớp theo tên kho).

    Trả về {'map': {branch_id: {'warehouse_id','location_id','name'}}, 'created': [...]}.
    Ở dry_run chỉ trả kế hoạch, không ghi Odoo.
    """
    branch_filter = set(branch_filter) if branch_filter else None
    branches = _inventory_branches(retailer, branch_filter)

    existing = _execute(
        'stock.warehouse', 'search_read', [],
        fields=['id', 'name', 'code', 'lot_stock_id'],
    ) or []
    by_name = {(w.get('name') or '').strip().lower(): w for w in existing}
    used_codes = {(w.get('code') or '').strip() for w in existing if w.get('code')}

    result = {'map': {}, 'created': [], 'reused': []}
    for bid, name in sorted(branches.items(), key=lambda kv: kv[1]):
        match = by_name.get(name.lower())
        if match:
            loc = match.get('lot_stock_id')
            result['map'][bid] = {
                'warehouse_id': match['id'],
                'location_id': loc[0] if isinstance(loc, (list, tuple)) else loc,
                'name': name,
            }
            result['reused'].append(name)
            continue

        if dry_run:
            result['created'].append({'name': name, 'code': '(dry-run)'})
            result['map'][bid] = {'warehouse_id': None, 'location_id': None, 'name': name}
            continue

        code = _unique_warehouse_code(_ascii_slug(name) or f'KV{bid}', used_codes)
        wid = _execute('stock.warehouse', 'create', {'name': name, 'code': code})
        rec = _execute(
            'stock.warehouse', 'read', [wid], fields=['id', 'name', 'lot_stock_id'],
        )[0]
        loc = rec.get('lot_stock_id')
        result['map'][bid] = {
            'warehouse_id': wid,
            'location_id': loc[0] if isinstance(loc, (list, tuple)) else loc,
            'name': name,
        }
        result['created'].append({'name': name, 'code': code})
        by_name[name.lower()] = rec
    return result


# ------------------------------- DANH MỤC / CATEGORY -----------------------


def _load_category_index() -> tuple[dict, list]:
    """Trả về ((parent_id_or_0, name_lower) -> id, records)."""
    records = _execute(
        'product.category', 'search_read', [],
        fields=['id', 'name', 'parent_id'],
    ) or []
    index = {}
    for rec in records:
        parent = rec.get('parent_id')
        pid = parent[0] if isinstance(parent, (list, tuple)) else 0
        index[(pid or 0, (rec.get('name') or '').strip().lower())] = rec['id']
    return index, records


def ensure_category_tree(retailer: str, *, dry_run: bool = False) -> dict:
    """Tạo nhóm gốc 'KiotViet' + cây danh mục con từ category_path.

    Trả về {'path_map': {category_path: categ_id}, 'created': [...], 'root_id': id}.
    """
    paths = (
        KvProduct.objects
        .filter(retailer=retailer, is_deleted=False)
        .exclude(is_active=False)
        .values_list('category_path', flat=True)
        .distinct()
    )

    index, _ = _load_category_index()
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

    root_id = _ensure(KV_CATEGORY_ROOT, None)

    path_map: dict[str, int] = {}
    for path in paths:
        parts = _split_category_path(path)
        parent = root_id
        last = root_id
        skipped = False
        for part in parts:
            cid = _ensure(part, parent)
            if cid is None and not dry_run:
                skipped = True
                break
            parent = cid
            last = cid
        if not skipped and last is not None:
            path_map[path or ''] = last
        elif dry_run:
            path_map[path or ''] = root_id
    return {'path_map': path_map, 'created': created, 'root_id': root_id}


# ------------------------------- SẢN PHẨM / PRODUCT ------------------------


def _representative_cost(retailer: str, product_kv_id: int) -> Decimal | None:
    invs = KvProductInventory.objects.filter(
        retailer=retailer, product_kiotviet_id=product_kv_id, is_deleted=False,
    ).exclude(cost__isnull=True).exclude(cost=0).values_list('cost', flat=True)
    for c in invs:
        d = _to_decimal(c)
        if d is not None and d > 0:
            return d
    return None


def _build_product_vals(kv: KvProduct, categ_id, retailer: str, product_type: str) -> dict:
    vals = {
        'name': (kv.name or kv.code or '').strip() or kv.code,
        'default_code': _norm_code(kv.code),
        'list_price': float(kv.base_price) if kv.base_price is not None else 0.0,
        'sale_ok': True,
        'purchase_ok': True,
        'type': 'consu',
    }
    if product_type == 'storable':
        vals['is_storable'] = True
    if categ_id:
        vals['categ_id'] = categ_id
    bar = _norm_code(kv.bar_code)
    if bar:
        vals['barcode'] = bar
    cost = _representative_cost(retailer, kv.kiotviet_id)
    if cost is not None:
        vals['standard_price'] = float(cost)
    return vals


@dataclass
class PushResult:
    retailer: str = ''
    dry_run: bool = True
    warehouses_created: list = field(default_factory=list)
    categories_created: list = field(default_factory=list)
    products_total: int = 0
    products_created: int = 0
    products_updated: int = 0
    products_skipped: int = 0
    products_failed: list = field(default_factory=list)
    stock_applied: int = 0
    stock_failed: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            'dry_run': self.dry_run,
            'warehouses_created': len(self.warehouses_created),
            'categories_created': len(self.categories_created),
            'products_total': self.products_total,
            'products_created': self.products_created,
            'products_updated': self.products_updated,
            'products_skipped': self.products_skipped,
            'products_failed': len(self.products_failed),
            'stock_applied': self.stock_applied,
            'stock_failed': len(self.stock_failed),
        }


def _create_products_batch(vals_list: list[dict], result: PushResult) -> None:
    """Tạo product.template theo lô; nếu lô lỗi thì tạo lẻ để cô lập bản ghi hỏng."""
    if not vals_list:
        return
    try:
        ids = _execute('product.template', 'create', vals_list)
        result.products_created += len(ids if isinstance(ids, list) else [ids])
        return
    except Exception:
        pass
    for vals in vals_list:
        try:
            _execute('product.template', 'create', vals)
            result.products_created += 1
        except Exception as exc:  # noqa: BLE001
            result.products_failed.append({'code': vals.get('default_code'), 'error': str(exc)[:200]})


def push_products(
    retailer: str | None = None,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    with_stock: bool = True,
    update_existing: bool = True,
    branch_filter=None,
    product_type: str = 'storable',
    progress=None,
) -> PushResult:
    """Đẩy danh mục + sản phẩm (+ tồn kho) từ KiotViet sang Odoo.

    Idempotent: khớp theo default_code. Chạy lại chỉ cập nhật/thêm mới.
    """
    retailer = retailer if retailer is not None else current_retailer()
    result = PushResult(retailer=retailer, dry_run=dry_run)

    def _log(msg, pct=None):
        if progress:
            progress(msg, pct)

    # 1) Danh mục
    _log('Chuẩn bị cây danh mục...', 3)
    cat = ensure_category_tree(retailer, dry_run=dry_run)
    result.categories_created = cat['created']
    path_map = cat['path_map']
    root_id = cat['root_id']

    # 2) Kho
    _log('Chuẩn bị kho...', 6)
    wh = ensure_warehouses(retailer, branch_filter, dry_run=dry_run)
    result.warehouses_created = wh['created']
    branch_loc = {bid: info['location_id'] for bid, info in wh['map'].items()}

    # 3) Sản phẩm
    qs = (
        KvProduct.objects
        .filter(retailer=retailer, is_deleted=False)
        .exclude(is_active=False)
        .exclude(code='')
        .order_by('code', 'kiotviet_id')
    )
    if limit:
        qs = qs[:limit]
    products = list(qs)
    result.products_total = len(products)

    # gom theo code, loại trùng trong KiotViet (giữ bản đầu)
    seen_codes: set[str] = set()
    unique_products: list[KvProduct] = []
    for p in products:
        code = _norm_code(p.code)
        if code in seen_codes:
            continue
        seen_codes.add(code)
        unique_products.append(p)

    existing = fetch_odoo_products_by_code(seen_codes)

    to_create: list[dict] = []
    for idx, kv in enumerate(unique_products, 1):
        code = _norm_code(kv.code)
        categ_id = path_map.get(kv.category_path or '', root_id)
        odoo_records = existing.get(code)

        if odoo_records:
            if not update_existing:
                result.products_skipped += 1
                continue
            if dry_run:
                result.products_updated += 1
                continue
            odoo = odoo_records[0]
            vals = _build_product_vals(kv, categ_id, retailer, product_type)
            vals.pop('default_code', None)  # không đổi khóa
            try:
                # product.product.id -> ghi lên product.template gốc
                tmpl_id = _execute(
                    'product.product', 'read', [odoo['id']], fields=['product_tmpl_id'],
                )[0]['product_tmpl_id']
                tmpl_id = tmpl_id[0] if isinstance(tmpl_id, (list, tuple)) else tmpl_id
                _execute('product.template', 'write', [tmpl_id], vals)
                result.products_updated += 1
            except Exception as exc:  # noqa: BLE001
                result.products_failed.append({'code': code, 'error': str(exc)[:200]})
            continue

        if dry_run:
            result.products_created += 1
            continue

        to_create.append(_build_product_vals(kv, categ_id, retailer, product_type))
        if len(to_create) >= _PRODUCT_CREATE_BATCH:
            _create_products_batch(to_create, result)
            to_create = []
            total = max(1, len(unique_products))
            pct = 6 + int((result.products_created / total) * 74)
            _log(f'Đã tạo {result.products_created} SP...', min(80, pct))

    if to_create:
        _create_products_batch(to_create, result)
    _log(f'Xong sản phẩm: tạo {result.products_created}, cập nhật {result.products_updated}.', 80)

    # 4) Tồn kho
    if with_stock and not dry_run:
        _log('Đang set tồn kho theo kho...', 82)
        push_stock(retailer, branch_loc, seen_codes, result, progress=progress)
    elif with_stock and dry_run:
        _log('(dry-run) Bỏ qua ghi tồn kho.', 99)

    return result


_STOCK_APPLY_BATCH = 500


def push_stock(retailer: str, branch_loc: dict, codes: set[str], result: PushResult, *, progress=None) -> None:
    """Set on_hand cho từng (SP, kho) qua stock.quant inventory mode. Idempotent.

    Tối ưu: ghi inventory_quantity từng dòng (nhẹ, chỉ ghi DB) rồi gọi
    action_apply_inventory THEO LÔ (nặng) — giảm số lần apply từ hàng nghìn
    xuống vài chục, nhanh hơn ~1-2 bậc so với apply từng dòng.
    """
    valid_locs = {bid: loc for bid, loc in branch_loc.items() if loc}
    if not valid_locs:
        return

    variants = fetch_odoo_products_by_code(codes)
    code_to_pid = {c: recs[0]['id'] for c, recs in variants.items() if recs}
    loc_ids = list(valid_locs.values())

    invs = list(
        KvProductInventory.objects
        .filter(retailer=retailer, is_deleted=False, branch_kiotviet_id__in=list(valid_locs.keys()))
        .exclude(on_hand__isnull=True)
        .exclude(on_hand=0)
        .values('product_kiotviet_id', 'branch_kiotviet_id', 'on_hand')
    )
    kv_id_to_code = dict(
        KvProduct.objects
        .filter(retailer=retailer, kiotviet_id__in=[i['product_kiotviet_id'] for i in invs])
        .values_list('kiotviet_id', 'code')
    )

    # (pid, loc) -> qty cần đặt
    targets: dict[tuple[int, int], float] = {}
    for row in invs:
        code = _norm_code(kv_id_to_code.get(row['product_kiotviet_id']))
        pid = code_to_pid.get(code)
        loc = valid_locs.get(row['branch_kiotviet_id'])
        if not pid or not loc:
            continue
        targets[(pid, loc)] = float(row['on_hand'] or 0)

    total = max(1, len(targets))
    if progress:
        progress(f'Chuẩn bị ghi {total} dòng tồn kho...', 83)

    # Nạp trước quant hiện có để biết dòng nào update / dòng nào tạo mới
    pids = list({pid for pid, _ in targets})
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
            p = q['product_id'][0] if isinstance(q['product_id'], (list, tuple)) else q['product_id']
            l = q['location_id'][0] if isinstance(q['location_id'], (list, tuple)) else q['location_id']
            existing_quants[(p, l)] = q['id']

    quant_ids: list[int] = []
    done = 0
    for (pid, loc), qty in targets.items():
        try:
            qid = existing_quants.get((pid, loc))
            if qid:
                _execute('stock.quant', 'write', [qid], {'inventory_quantity': qty},
                         context={'inventory_mode': True})
            else:
                qid = _execute(
                    'stock.quant', 'create',
                    {'product_id': pid, 'location_id': loc, 'inventory_quantity': qty},
                    context={'inventory_mode': True},
                )
            quant_ids.append(qid)
            done += 1
            if progress and done % 500 == 0:
                pct = 83 + int((done / total) * 10)
                progress(f'Đã ghi {done}/{total} dòng (chưa áp dụng)...', min(93, pct))
        except Exception as exc:  # noqa: BLE001
            result.stock_failed.append({'pid': pid, 'loc': loc, 'error': str(exc)[:150]})

    # Áp dụng tồn kho theo lô (bước nặng nhất, nhưng gộp nên nhanh)
    if progress:
        progress(f'Áp dụng tồn kho theo lô ({len(quant_ids)} dòng)...', 94)
    for i in range(0, len(quant_ids), _STOCK_APPLY_BATCH):
        batch = quant_ids[i:i + _STOCK_APPLY_BATCH]
        try:
            _safe_apply_inventory(batch)
            result.stock_applied += len(batch)
        except Exception as exc:  # noqa: BLE001
            result.stock_failed.append({'batch_start': i, 'error': str(exc)[:150]})
        if progress:
            pct = 94 + int(((i + len(batch)) / max(1, len(quant_ids))) * 5)
            progress(f'Đã áp dụng {min(i + len(batch), len(quant_ids))}/{len(quant_ids)} dòng tồn...', min(99, pct))
