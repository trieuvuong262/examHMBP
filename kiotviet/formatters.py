"""Chuẩn hóa dữ liệu KiotViet cho template."""

import re

import bleach
from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import mark_safe

_DESCRIPTION_ALLOWED_TAGS = [
    'p', 'br', 'strong', 'b', 'em', 'i', 'ul', 'ol', 'li', 'span', 'div',
]
_DESCRIPTION_ALLOWED_ATTRIBUTES = {
    '*': ['class'],
}


def _looks_like_html(text: str) -> bool:
    return bool(re.search(r'</?[a-z][\w-]*\b', text, re.IGNORECASE))


def format_description_html(raw: str | None) -> str:
    """Mô tả SP từ KiotViet — HTML an toàn hoặc xuống dòng cho text thuần."""
    text = (raw or '').strip()
    if not text:
        return ''
    if _looks_like_html(text):
        return bleach.clean(
            text,
            tags=_DESCRIPTION_ALLOWED_TAGS,
            attributes=_DESCRIPTION_ALLOWED_ATTRIBUTES,
            strip=True,
        )
    return mark_safe(escape(text).replace('\n', '<br>'))


def _detail_stock_branch_allowlist() -> tuple[str, ...]:
    raw = (getattr(settings, 'KIOTVIET_DETAIL_STOCK_BRANCHES', '') or '').strip()
    if not raw:
        return (
            'Chi nhánh trung tâm',
            'Xưởng sản xuất',
            'Đơn sản xuất',
        )
    return tuple(part.strip() for part in raw.split(',') if part.strip())


def _branch_allowed_for_detail_stock(branch_name: str, allowed: tuple[str, ...]) -> bool:
    normalized = (branch_name or '').strip().casefold()
    return any(normalized == name.strip().casefold() for name in allowed)


def _detail_stock_branch_sort_key(branch_name: str, allowed: tuple[str, ...]) -> int:
    normalized = (branch_name or '').strip().casefold()
    for index, name in enumerate(allowed):
        if normalized == name.strip().casefold():
            return index
    return len(allowed)


def format_customer_row(row: dict) -> dict:
    gender = row.get('gender')
    if gender is True:
        gender_label = 'Nam'
    elif gender is False:
        gender_label = 'Nữ'
    else:
        gender_label = '—'
    return {
        'id': row.get('id'),
        'code': _dash(row.get('code')),
        'name': _dash(row.get('name')),
        'contact_number': _dash(row.get('contactNumber')),
        'email': _dash(row.get('email')),
        'address': _dash(row.get('address')),
        'debt': row.get('debt'),
        'total_revenue': row.get('totalRevenue'),
        'reward_point': row.get('rewardPoint'),
        'gender_label': gender_label,
        'modified_date': row.get('modifiedDate'),
    }


def _dash(value) -> str:
    if value is None or value == '':
        return '—'
    return str(value)


def _product_type_label(value) -> str:
    labels = {
        1: 'Hàng combo',
        2: 'Hàng thường',
        3: 'Dịch vụ',
    }
    if value is None:
        return '—'
    return labels.get(int(value), str(value))


def _bool_status(value) -> dict:
    if value is True:
        return {'label': 'Có', 'badge_class': 'bg-success'}
    if value is False:
        return {'label': 'Không', 'badge_class': 'bg-secondary'}
    return {'label': '—', 'badge_class': 'bg-light text-dark border'}


def _aggregate_bool(values: list) -> bool | str | None:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    if all(cleaned):
        return True
    if not any(cleaned):
        return False
    return 'mixed'


def _aggregate_status(values: list) -> dict:
    agg = _aggregate_bool(values)
    if agg == 'mixed':
        return {'label': 'Khác nhau', 'badge_class': 'bg-warning text-dark'}
    return _bool_status(agg)


def format_order_row(row: dict) -> dict:
    return {
        'id': row.get('id'),
        'code': _dash(row.get('code')),
        'purchase_date': row.get('purchaseDate'),
        'customer_code': _dash(row.get('customerCode')),
        'customer_name': _dash(row.get('customerName')),
        'branch_name': _dash(row.get('branchName')),
        'total': row.get('total'),
        'total_payment': row.get('totalPayment'),
        'status_value': _dash(row.get('statusValue')),
        'sold_by_name': _dash(row.get('soldByName')),
    }


def format_invoice_row(row: dict) -> dict:
    return {
        'id': row.get('id'),
        'code': _dash(row.get('code')),
        'purchase_date': row.get('purchaseDate'),
        'customer_code': _dash(row.get('customerCode')),
        'customer_name': _dash(row.get('customerName')),
        'branch_name': _dash(row.get('branchName')),
        'total': row.get('total'),
        'total_payment': row.get('totalPayment'),
        'status_value': _dash(row.get('statusValue')),
        'sold_by_name': _dash(row.get('soldByName')),
    }


def format_line_items(raw_items) -> list[dict]:
    if not raw_items:
        return []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    lines = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        lines.append({
            'product_code': _dash(item.get('productCode')),
            'product_name': _dash(item.get('productName')),
            'quantity': item.get('quantity'),
            'price': item.get('price'),
            'discount': item.get('discount'),
            'note': _dash(item.get('note')),
        })
    return lines


def format_order_detail(raw: dict) -> dict:
    row = format_order_row(raw)
    row.update({
        'description': _dash(raw.get('description')),
        'discount': raw.get('discount'),
        'created_date': raw.get('createdDate'),
        'modified_date': raw.get('modifiedDate'),
        'lines': format_line_items(raw.get('orderDetails')),
        'payments': raw.get('payments') or [],
    })
    return row


def format_invoice_detail(raw: dict) -> dict:
    row = format_invoice_row(raw)
    row.update({
        'created_date': raw.get('createdDate'),
        'modified_date': raw.get('modifiedDate'),
        'lines': format_line_items(raw.get('invoiceDetails')),
        'payments': raw.get('payments') or [],
    })
    return row


def _first_product_image(row: dict) -> str:
    for item in row.get('images') or []:
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            url = (item.get('Image') or item.get('image') or item.get('url') or '').strip()
            if url:
                return url
    return ''


def _first_variant_image(variant: dict) -> str:
    return _first_product_image(variant)


def format_product_row(row: dict) -> dict:
    return {
        'id': row.get('id'),
        'code': _dash(row.get('code')),
        'name': _dash(row.get('name')),
        'full_name': _dash(row.get('fullName')),
        'bar_code': _dash(row.get('barCode')),
        'category_name': _dash(row.get('categoryName')),
        'unit': _dash(row.get('unit')),
        'base_price': row.get('basePrice'),
        'allows_sale': row.get('allowsSale'),
        'is_active': row.get('isActive'),
        'image_url': _first_product_image(row),
    }


def format_product_group_row(group) -> dict:
    """Nhóm SP (nhiều size / mã)."""
    image_url = (group.image_urls or [None])[0] or ''
    if group.variant_count > 1:
        code_label = f'{group.variant_count} mã'
        if group.codes:
            code_label = f'{group.codes[0]} … (+{group.variant_count - 1})'
    else:
        code_label = _dash(group.codes[0] if group.codes else '')
    price = group.min_price
    if group.min_price is not None and group.max_price is not None and group.min_price != group.max_price:
        price = group.min_price  # template can show range
    return {
        'id': group.representative_id,
        'code': code_label,
        'name': _dash(group.name),
        'category_name': _dash(group.category_name),
        'category_path': _dash(group.category_path),
        'category_path_parts': group.category_path_parts or [],
        'category_kiotviet_id': group.category_kiotviet_id,
        'unit': _dash(group.unit),
        'base_price': price,
        'min_price': group.min_price,
        'max_price': group.max_price,
        'image_url': image_url,
        'variant_count': group.variant_count,
        'total_on_hand': group.total_on_hand,
        'total_reserved': group.total_reserved,
        'variants': [
            {
                'id': variant.id,
                'code': _dash(variant.code) if variant.code else '—',
                'size_label': variant.size_label,
                'on_hand': variant.on_hand,
                'reserved': variant.reserved,
                'base_price': variant.base_price,
                'image_url': variant.image_url or '',
            }
            for variant in (group.variants or [])
        ],
        'is_group': group.variant_count > 1,
        'allows_sale_status': _aggregate_status(group.allows_sale_values),
        'is_active_status': _aggregate_status(group.is_active_values),
    }


def _build_branch_stock_matrix(variants: list[dict]) -> dict:
    """Gộp tồn theo chi nhánh; nhóm nhiều size thì thêm cột theo size."""
    allowed_branches = _detail_stock_branch_allowlist()
    show_size_columns = len(variants) > 1
    columns = []
    if show_size_columns:
        for variant in variants:
            size_label = variant.get('size_label') or '—'
            code = variant.get('code') or '—'
            label = size_label if size_label != '—' else code
            columns.append({'code': code, 'label': label})

    branch_map: dict[str, dict] = {}
    for variant in variants:
        code = variant.get('code') or '—'
        for inv in variant.get('inventories') or []:
            branch_name = inv.get('branch_name') or '—'
            if not _branch_allowed_for_detail_stock(branch_name, allowed_branches):
                continue
            bucket = branch_map.setdefault(branch_name, {
                'cells': {},
                'on_hand': 0.0,
                'reserved': 0.0,
                'cost': inv.get('cost'),
            })
            on_hand = float(inv.get('on_hand') or 0)
            reserved = float(inv.get('reserved') or 0)
            bucket['cells'][code] = bucket['cells'].get(code, 0.0) + on_hand
            bucket['on_hand'] += on_hand
            bucket['reserved'] += reserved
            if inv.get('cost') is not None:
                bucket['cost'] = inv.get('cost')

    rows = []
    for branch_name in sorted(
        branch_map.keys(),
        key=lambda value: _detail_stock_branch_sort_key(value, allowed_branches),
    ):
        bucket = branch_map[branch_name]
        rows.append({
            'branch_name': branch_name,
            'cells': [bucket['cells'].get(col['code']) for col in columns],
            'on_hand': bucket['on_hand'],
            'cost': bucket.get('cost'),
        })

    return {
        'columns': columns,
        'rows': rows,
        'has_data': bool(rows),
        'show_size_columns': show_size_columns,
    }


def format_product_group_detail(raw: dict) -> dict:
    raw_variants = raw.get('variants') or []
    variants = []
    allows_sale_values = []
    active_values = []
    variant_values = []
    product_types = []
    modified_dates = []
    descriptions = []
    total_reserved = 0.0
    for v in raw_variants:
        allows_sale = v.get('allowsSale')
        is_active = v.get('isActive')
        has_variants = v.get('hasVariants')
        product_type = v.get('productType')
        allows_sale_values.append(allows_sale)
        active_values.append(is_active)
        variant_values.append(has_variants)
        if product_type is not None:
            product_types.append(int(product_type))
        if v.get('modifiedDate'):
            modified_dates.append(v.get('modifiedDate'))
        if (v.get('description') or '').strip():
            descriptions.append((v.get('description') or '').strip())
        inventories = format_inventory_rows(v)
        for inv in inventories:
            total_reserved += float(inv.get('reserved') or 0)
        variants.append({
            'id': v.get('id'),
            'code': _dash(v.get('code')),
            'size_label': _dash(v.get('size_label')) if v.get('size_label') else '—',
            'base_price': v.get('basePrice'),
            'bar_code': _dash(v.get('barCode')),
            'stock_total': v.get('stock_total'),
            'image_url': _first_variant_image(v),
            'inventories': inventories,
            'attributes': v.get('attributes') or [],
            'allows_sale_status': _bool_status(allows_sale),
            'is_active_status': _bool_status(is_active),
            'product_type_label': _product_type_label(product_type),
            'modified_date': v.get('modifiedDate'),
            'description': _dash(v.get('description')),
        })
    images = raw.get('images') or []
    unique_types = sorted(set(product_types))
    if len(unique_types) == 1:
        product_type_label = _product_type_label(unique_types[0])
    elif unique_types:
        product_type_label = 'Khác nhau'
    else:
        product_type_label = '—'
    return {
        'name': _dash(raw.get('name')),
        'category_name': _dash(raw.get('category_name')),
        'category_path': _dash(raw.get('category_path')),
        'category_path_parts': raw.get('category_path_parts') or [],
        'category_kiotviet_id': raw.get('category_kiotviet_id'),
        'unit': _dash(raw.get('unit')),
        'variant_count': raw.get('variant_count', 1),
        'total_on_hand': raw.get('total_on_hand'),
        'total_reserved': total_reserved,
        'min_price': raw.get('min_price'),
        'max_price': raw.get('max_price'),
        'images': images,
        'image_url': images[0] if images else '',
        'variants': variants,
        'is_group': raw.get('variant_count', 1) > 1,
        'allows_sale_status': _aggregate_status(allows_sale_values),
        'is_active_status': _aggregate_status(active_values),
        'has_variants_status': _aggregate_status(variant_values),
        'product_type_label': product_type_label,
        'modified_date': max(modified_dates) if modified_dates else None,
        'description_html': format_description_html(descriptions[0] if descriptions else ''),
        'stock_matrix': _build_branch_stock_matrix(variants),
    }


def format_inventory_rows(product: dict) -> list[dict]:
    """Mở rộng tồn theo chi nhánh từ product hoặc productOnHands."""
    code = _dash(product.get('code'))
    name = _dash(product.get('name') or product.get('fullName'))
    product_id = product.get('id')
    rows = []
    for inv in product.get('inventories') or []:
        if not isinstance(inv, dict):
            continue
        on_hand = inv.get('onHand')
        if on_hand is None:
            on_hand = inv.get('onhand')
        reserved = inv.get('reserved')
        rows.append({
            'product_id': product_id,
            'product_code': code,
            'product_name': name,
            'branch_id': inv.get('branchId'),
            'branch_name': _dash(inv.get('branchName')),
            'on_hand': on_hand,
            'reserved': reserved,
            'cost': inv.get('cost'),
            'modified_date': inv.get('modifiedDate'),
        })
    return rows


def format_product_detail(raw: dict) -> dict:
    row = format_product_row(raw)
    images = []
    for item in raw.get('images') or []:
        if isinstance(item, str) and item.strip():
            images.append(item.strip())
        elif isinstance(item, dict):
            url = (item.get('Image') or item.get('image') or item.get('url') or '').strip()
            if url:
                images.append(url)
    row.update({
        'description': _dash(raw.get('description')),
        'weight': raw.get('weight'),
        'created_date': raw.get('createdDate'),
        'modified_date': raw.get('modifiedDate'),
        'inventories': format_inventory_rows(raw),
        'images': images,
    })
    return row


def format_purchase_order_row(row: dict) -> dict:
    return {
        'id': row.get('id'),
        'code': _dash(row.get('code')),
        'purchase_date': row.get('purchaseDate'),
        'branch_name': _dash(row.get('branchName')),
        'supplier_code': _dash(row.get('supplierCode')),
        'supplier_name': _dash(row.get('supplierName')),
        'total': row.get('total'),
        'status_value': _dash(row.get('statusValue')),
    }


def format_purchase_lines(raw_items) -> list[dict]:
    if not raw_items:
        return []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    lines = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        lines.append({
            'product_code': _dash(item.get('productCode') or item.get('ProductCode')),
            'product_name': _dash(item.get('productName')),
            'quantity': item.get('quantity'),
            'price': item.get('price'),
            'discount': item.get('discount'),
        })
    return lines


def format_purchase_order_detail(raw: dict) -> dict:
    row = format_purchase_order_row(raw)
    row.update({
        'partner_type': _dash(raw.get('partnerType')),
        'purchase_name': _dash(raw.get('purchaseName')),
        'lines': format_purchase_lines(raw.get('purchaseOrderDetails')),
    })
    return row
