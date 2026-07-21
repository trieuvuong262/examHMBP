"""Cột bảng + sắp xếp danh sách Sản xuất — cùng pattern Kho NPL."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.http import HttpRequest

META_CREATED_BY: dict[str, Any] = {
    'key': 'created_by',
    'label': 'Người tạo',
    'weight': 90,
    'default': False,
    'sortable': True,
}
META_CREATED_AT: dict[str, Any] = {
    'key': 'created_at',
    'label': 'Tạo lúc',
    'weight': 100,
    'default': False,
    'sortable': True,
}
ACTIONS_COL: dict[str, Any] = {
    'key': 'actions',
    'label': '',
    'weight': 70,
    'default': True,
    'required': True,
    'sortable': False,
    'align': 'end',
}


def _col(
    key: str,
    label: str,
    *,
    weight: int = 100,
    default: bool = True,
    required: bool = False,
    sortable: bool = True,
    align: str = '',
) -> dict[str, Any]:
    return {
        'key': key,
        'label': label,
        'weight': weight,
        'default': default,
        'required': required,
        'sortable': sortable,
        'align': align,
    }


def _cols(*items: dict[str, Any], meta: bool = True, actions: bool = False) -> list[dict[str, Any]]:
    out = list(items)
    if meta:
        out.extend([META_CREATED_BY, META_CREATED_AT])
    if actions:
        out.append(ACTIONS_COL)
    return out


def _spec(columns: list[dict[str, Any]], sort_fields: dict[str, str], *, default_sort: str = 'code') -> dict[str, Any]:
    return {'columns': columns, 'sort_fields': sort_fields, 'default_sort': default_sort}


SX_LIST_GRIDS: dict[str, dict[str, Any]] = {
    'dispatch_mo': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('product', 'Sản phẩm', weight=140),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('order_date', 'Ngày', weight=90),
            _col('due_date', 'Hạn', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'product': 'product_code',
            'qty': 'qty',
            'order_date': 'order_date',
            'due_date': 'due_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='order_date',
    ),
    'disassembly': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('product', 'SP tháo', weight=130),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('mo', 'Lệnh sản xuất', weight=110),
            _col('order_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'product': 'product_code',
            'qty': 'qty',
            'mo': 'source_mo__code',
            'order_date': 'order_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='order_date',
    ),
    'dispatch_material_issue': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('request_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            _col('issue_doc', 'Phiếu xuất', weight=110),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'request_date': 'request_date',
            'status': 'status',
            'issue_doc': 'npl_issue_doc_code',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'dispatch_prod_stat': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('stat_date', 'Ngày', weight=90),
            _col('process', 'Công đoạn', weight=110),
            _col('qty_good', 'Đạt', weight=70, align='end'),
            _col('qty_defect', 'Lỗi', weight=70, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'stat_date': 'stat_date',
            'process': 'process_name',
            'qty_good': 'qty_good',
            'qty_defect': 'qty_defect',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='stat_date',
    ),
    'dispatch_fg_receipt': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('request_date', 'Ngày', weight=90),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('status', 'Trạng thái', weight=100),
            _col('kv_doc', 'Phiếu KV', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'request_date': 'request_date',
            'qty': 'qty',
            'status': 'status',
            'kv_doc': 'kv_receipt_code',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'npl_surplus': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('material', 'NPL', weight=130),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('source', 'Lệnh SX / tháo dỡ', weight=130),
            _col('recorded_at', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            _col('stock_adj', 'ĐC kho', weight=90),
            actions=True,
        ),
        {
            'code': 'code',
            'material': 'material_code',
            'qty': 'qty',
            'source': 'production_order__code',
            'recorded_at': 'recorded_at',
            'status': 'status',
            'stock_adj': 'stock_adjustment_code',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'wip_handover': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('from_process', 'Từ công đoạn', weight=110),
            _col('to_process', 'Đến công đoạn', weight=110),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('handover_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'from_process': 'from_process',
            'to_process': 'to_process',
            'qty': 'qty',
            'handover_date': 'handover_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'wip_return': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('from_process', 'Từ công đoạn', weight=110),
            _col('to_process', 'Về công đoạn', weight=110),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('return_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'handover__production_order__code',
            'from_process': 'from_process',
            'to_process': 'to_process',
            'qty': 'qty',
            'return_date': 'return_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'qc_request': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('product', 'Mã sản phẩm', weight=110),
            _col('process', 'Công đoạn', weight=110),
            _col('request_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'product': 'product_code',
            'process': 'stage_name',
            'request_date': 'request_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'qc_sheet': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('qc_request', 'Yêu cầu kiểm tra', weight=130),
            _col('inspected_at', 'Ngày kiểm', weight=100),
            _col('standard', 'Bộ tiêu chuẩn', weight=120),
            _col('qty_sample', 'Mẫu', weight=70, align='end'),
            _col('qty_pass', 'Đạt', weight=70, align='end'),
            _col('qty_fail', 'Lỗi', weight=70, align='end'),
            _col('result', 'Kết luận', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'qc_request': 'qc_request__code',
            'inspected_at': 'inspected_at',
            'standard': 'standard_set',
            'qty_sample': 'qty_sample',
            'qty_pass': 'qty_pass',
            'qty_fail': 'qty_fail',
            'result': 'result',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='inspected_at',
    ),
    'qc_alert': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('alert_type', 'Loại', weight=90),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('process', 'Công đoạn', weight=110),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('message', 'Nội dung', weight=150),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'alert_type': 'alert_type',
            'mo': 'production_order__code',
            'process': 'process_name',
            'qty': 'qty',
            'message': 'message',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='created_at',
    ),
    'work_assignment': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('title', 'Tiêu đề', weight=130),
            _col('assignee', 'Tổ / công đoạn / người', weight=150),
            _col('work_task', 'WorkTask', weight=100),
            _col('due_date', 'Hạn', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'title': 'title',
            'assignee': 'assignee_label',
            'work_task': 'work_task_code',
            'due_date': 'due_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'packing': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('lot', 'Lô', weight=90),
            _col('pack_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'qty': 'qty',
            'lot': 'lot_code',
            'pack_date': 'pack_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'subcontract': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('vendor', 'NCC Gia công', weight=130),
            _col('product', 'SP', weight=110),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('order_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'vendor': 'vendor_name',
            'product': 'product_code',
            'qty': 'qty',
            'order_date': 'order_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'plan_overall': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('name', 'Tên', weight=140),
            _col('date_from', 'Từ', weight=90),
            _col('date_to', 'Đến', weight=90),
            _col('source', 'Nguồn', weight=100),
            _col('line_count', 'Dòng SP', weight=80, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'name': 'name',
            'date_from': 'date_from',
            'date_to': 'date_to',
            'source': 'source',
            'line_count': 'pk',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='date_from',
    ),
    'plan_detail': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('name', 'Tên', weight=140),
            _col('overall', 'Kế hoạch tổng thể nguồn', weight=140),
            _col('period', 'Kỳ', weight=120),
            _col('line_count', 'Dòng SP', weight=80, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'name': 'name',
            'overall': 'overall_plan__code',
            'period': 'date_from',
            'line_count': 'pk',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='date_from',
    ),
    'plan_npl': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('name', 'Tên', weight=140),
            _col('overall', 'Kế hoạch tổng thể nguồn', weight=140),
            _col('line_count', 'Dòng NPL', weight=80, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'name': 'name',
            'overall': 'overall_plan__code',
            'line_count': 'pk',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'npl_purchase_request': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('plan', 'Kế hoạch NPL', weight=130),
            _col('request_date', 'Ngày yêu cầu', weight=100),
            _col('due_date', 'Hạn', weight=90),
            _col('line_count', 'Dòng', weight=70, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'plan': 'npl_plan__code',
            'request_date': 'request_date',
            'due_date': 'due_date',
            'line_count': 'pk',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'purchase_order': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('supplier', 'NCC', weight=130),
            _col('pr', 'Yêu cầu mua NPL nguồn', weight=140),
            _col('total', 'Tổng tiền', weight=90, align='end'),
            _col('kv_receipt', 'Phiếu nhập KiotViet', weight=120),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'supplier': 'supplier_name',
            'pr': 'purchase_request__code',
            'total': 'total_amount',
            'kv_receipt': 'kv_receipt_code',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'costing_sheet': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('name', 'Tên', weight=140),
            _col('period', 'Kỳ', weight=120),
            _col('line_count', 'Dòng', weight=80, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'name': 'name',
            'period': 'date_from',
            'line_count': 'pk',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='date_from',
    ),
    'costing_order': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('name', 'Tên', weight=130),
            _col('kv_order', 'Đơn KV', weight=110),
            _col('period', 'Kỳ', weight=120),
            _col('total', 'Tổng', weight=90, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'name': 'name',
            'kv_order': 'kv_order_code',
            'period': 'date_from',
            'total': 'total_cost',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='date_from',
    ),
    'costing_cost_type': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('name', 'Tên', weight=150),
            _col('category', 'Nhóm', weight=110),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'name': 'name',
            'category': 'category',
            'status': 'is_active',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'ncr': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('disposition', 'Hướng xử lý', weight=120),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'disposition': 'disposition',
            'qty': 'qty',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'actual_cost': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('mo', 'Lệnh sản xuất', weight=120),
            _col('material', 'Nguyên phụ liệu', weight=100, align='end'),
            _col('labor', 'Nhân công', weight=90, align='end'),
            _col('subcontract', 'Gia công', weight=90, align='end'),
            _col('total', 'Tổng', weight=90, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=True,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'material': 'material_cost',
            'labor': 'labor_cost',
            'subcontract': 'subcontract_cost',
            'total': 'total_cost',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'downtime': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('event_date', 'Ngày', weight=90),
            _col('reason', 'Lý do', weight=150),
            _col('minutes', 'Phút', weight=70, align='end'),
            _col('team', 'Tổ', weight=100),
            _col('mo', 'Lệnh sản xuất', weight=120),
            meta=False,
        ),
        {
            'code': 'code',
            'event_date': 'event_date',
            'reason': 'reason',
            'minutes': 'duration_minutes',
            'team': 'team_label',
            'mo': 'production_order__code',
        },
        default_sort='event_date',
    ),
    'team_hr': _spec(
        _cols(
            _col('employee_code', 'Mã NV', required=True),
            _col('employee_name', 'Tên NV', weight=140),
            _col('team', 'Tổ', weight=110),
            _col('status', 'Trạng thái', weight=90),
            meta=False,
        ),
        {
            'employee_code': 'employee_code',
            'employee_name': 'employee_name',
            'team': 'team_label',
            'status': 'is_active',
        },
    ),
    'capacity_catalog': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('name', 'Tên', weight=130),
            _col('team_label', 'Nhãn Thống kê sản xuất', weight=140),
            _col('capacity', 'Năng lực/ngày', weight=100, align='end'),
            _col('uom', 'Đơn vị tính', weight=80),
            _col('status', 'Trạng thái', weight=90),
            meta=True,
            actions=False,
        ),
        {
            'code': 'code',
            'name': 'name',
            'team_label': 'team_label',
            'capacity': 'capacity_per_day',
            'uom': 'uom_label',
            'status': 'is_active',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'bom_list': _spec(
        _cols(
            _col('product_code', 'Mã sản phẩm', required=True),
            _col('product_name', 'Tên', weight=140),
            _col('version', 'Phiên bản', weight=90),
            _col('status', 'Trạng thái', weight=100),
            _col('line_count', 'Dòng NPL', weight=80, align='end'),
            _col('step_count', 'Công đoạn', weight=80, align='end'),
            _col('updated_at', 'Cập nhật', weight=110),
            actions=True,
        ),
        {
            'product_code': 'tech_doc__product_code',
            'product_name': 'tech_doc__product_name',
            'version': 'version_label',
            'status': 'status',
            'line_count': 'line_count',
            'step_count': 'step_count',
            'updated_at': 'updated_at',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='updated_at',
    ),
    'doc_list': _spec(
        _cols(
            _col('product_code', 'Mã sản phẩm', required=True),
            _col('product_name', 'Tên', weight=150),
            _col('status', 'Trạng thái', weight=100),
            _col('updated_at', 'Cập nhật', weight=110),
            actions=True,
        ),
        {
            'product_code': 'product_code',
            'product_name': 'product_name',
            'status': 'status',
            'updated_at': 'updated_at',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='updated_at',
    ),
    'costing_bom': _spec(
        _cols(
            _col('product_code', 'Mã sản phẩm', required=True),
            _col('product_name', 'Tên', weight=140),
            _col('material', 'Nguyên phụ liệu', weight=100, align='end'),
            _col('labor', 'Nhân công', weight=90, align='end'),
            _col('overhead', 'Phụ phí', weight=90, align='end'),
            _col('total', 'Tổng GT', weight=90, align='end'),
            _col('sell_price', 'Giá bán', weight=90, align='end'),
            _col('margin', 'Biên', weight=80, align='end'),
            actions=True,
        ),
        {
            'product_code': 'product_code',
            'product_name': 'product_name',
        },
    ),
}


def parse_sx_list_sort(request: HttpRequest, list_key: str) -> tuple[str, str]:
    spec = SX_LIST_GRIDS.get(list_key) or {}
    sort_fields = spec.get('sort_fields') or {}
    default = spec.get('default_sort') or 'code'
    sort_key = (request.GET.get('sort') or default).strip()
    if sort_key not in sort_fields:
        sort_key = default
    sort_dir = (request.GET.get('dir') or 'desc').strip().lower()
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'
    return sort_key, sort_dir


def apply_sx_list_sort(qs: QuerySet, request: HttpRequest, list_key: str) -> QuerySet:
    spec = SX_LIST_GRIDS.get(list_key)
    if not spec:
        return qs
    sort_key, sort_dir = parse_sx_list_sort(request, list_key)
    field = spec['sort_fields'].get(sort_key)
    if not field:
        return qs
    prefix = '-' if sort_dir == 'desc' else ''
    return qs.order_by(f'{prefix}{field}', '-pk')


def sx_list_grid_context(request: HttpRequest, list_key: str) -> dict[str, Any]:
    spec = SX_LIST_GRIDS[list_key]
    cols = spec['columns']
    sort_key, sort_dir = parse_sx_list_sort(request, list_key)
    return {
        'list_key': list_key,
        'list_columns': cols,
        'total_col_weight': sum(c['weight'] for c in cols),
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'sx_default_sort_key': spec.get('default_sort') or 'code',
        'sx_list_table_id': f'sx-list-{list_key}',
        'sx_list_storage_key': f'san_xuat_{list_key}_visible_cols',
        'sx_col_btn_id': f'sx-col-btn-{list_key}',
        'sx_col_prefix': f'sx-col-{list_key}',
        'sx_col_toggle_class': f'sx-col-toggle-{list_key}',
    }


def build_qc_catalog_grid(fields: list[str], labels: list[str], *, list_key: str) -> dict[str, Any]:
    """Tạo cột động cho danh mục QC."""
    columns = [_col(fields[0], labels[0], required=True)]
    for field, label in zip(fields[1:], labels[1:]):
        columns.append(_col(field, label))
    columns.extend([META_CREATED_BY, META_CREATED_AT])
    sort_fields = {c['key']: c['key'] for c in columns if c.get('sortable', True)}
    SX_LIST_GRIDS[list_key] = _spec(columns, sort_fields)
    return {'list_columns': columns, 'total_col_weight': sum(c['weight'] for c in columns)}
