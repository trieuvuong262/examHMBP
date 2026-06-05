"""Chuẩn hóa dữ liệu KiotViet cho template."""


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
        'unit': _dash(group.unit),
        'base_price': price,
        'min_price': group.min_price,
        'max_price': group.max_price,
        'image_url': image_url,
        'variant_count': group.variant_count,
        'total_on_hand': group.total_on_hand,
        'is_group': group.variant_count > 1,
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
        variants.append({
            'id': v.get('id'),
            'code': _dash(v.get('code')),
            'size_label': _dash(v.get('size_label')) if v.get('size_label') else '—',
            'base_price': v.get('basePrice'),
            'bar_code': _dash(v.get('barCode')),
            'stock_total': v.get('stock_total'),
            'inventories': format_inventory_rows(v),
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
        'unit': _dash(raw.get('unit')),
        'variant_count': raw.get('variant_count', 1),
        'total_on_hand': raw.get('total_on_hand'),
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
        'description': descriptions[0] if descriptions else '—',
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
