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
