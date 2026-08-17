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
            _col('qty_done', 'Đã đạt', weight=80, align='end'),
            _col('team_label', 'Tổ / công đoạn', weight=110, default=False),
            _col('order_date', 'Ngày lập', weight=90),
            _col('due_date', 'Hạn', weight=90),
            _col('planned_start', 'Kế hoạch bắt đầu', weight=95, default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
        ),
        {
            'code': 'code',
            'product': 'product_code',
            'qty': 'qty',
            'qty_done': 'qty_done',
            'team_label': 'team_label',
            'order_date': 'order_date',
            'due_date': 'due_date',
            'planned_start': 'planned_start',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
        default_sort='order_date',
    ),
    'disassembly': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('product', 'Sản phẩm tháo', weight=130),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('mo', 'Lệnh sản xuất', weight=140, default=False),
            _col('order_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
        ),
        {
            'code': 'code',
            'product': 'product_code',
            'qty': 'qty',
            'mo': 'production_order__code',
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('request_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            _col('issue_doc', 'Phiếu xuất', weight=110, default=False),
            actions=False,
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('stat_date', 'Ngày', weight=90),
            _col('process', 'Công đoạn', weight=110),
            _col('qty_good', 'Đạt', weight=70, align='end'),
            _col('qty_defect', 'Lỗi', weight=70, align='end', default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('request_date', 'Ngày', weight=90),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('status', 'Trạng thái', weight=100),
            _col('kv_doc', 'Phiếu KV', weight=100, default=False),
            actions=False,
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
            _col('source', 'Lệnh sản xuất / tháo dỡ', weight=160),
            _col('recorded_at', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            _col('stock_adj', 'Điều chỉnh kho', weight=90, default=False),
            actions=False,
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('from_process', 'Từ công đoạn', weight=110),
            _col('to_process', 'Đến công đoạn', weight=110),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('handover_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('from_process', 'Từ công đoạn', weight=110),
            _col('to_process', 'Về công đoạn', weight=110),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('return_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('product', 'Mã sản phẩm', weight=110),
            _col('process', 'Công đoạn', weight=110, default=False),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('request_date', 'Ngày yêu cầu', weight=90),
            _col('due_date', 'Hạn', weight=90, default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
        ),
        {
            'code': 'code',
            'mo': 'production_order__code',
            'product': 'product_code',
            'process': 'stage_name',
            'qty': 'qty',
            'request_date': 'request_date',
            'due_date': 'due_date',
            'status': 'status',
            'created_by': 'created_by__username',
            'created_at': 'created_at',
        },
    ),
    'qc_sheet': _spec(
        _cols(
            _col('code', 'Mã', required=True),
            _col('qc_request', 'Yêu cầu kiểm tra', weight=150, default=False),
            _col('inspected_at', 'Ngày kiểm', weight=100),
            _col('standard', 'Bộ tiêu chuẩn', weight=120, default=False),
            _col('qty_sample', 'Mẫu', weight=70, align='end', default=False),
            _col('qty_pass', 'Đạt', weight=70, align='end'),
            _col('qty_fail', 'Lỗi', weight=70, align='end', default=False),
            _col('result', 'Kết luận', weight=100),
            actions=False,
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
            _col('alert_type', 'Loại', weight=90, default=False),
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('process', 'Công đoạn', weight=110),
            _col('defect_rate', 'Tỷ lệ lỗi', weight=90, align='end'),
            _col('tolerance_limit', 'Ngưỡng', weight=80, align='end', default=False),
            _col('message', 'Nội dung', weight=150, default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
        ),
        {
            'code': 'code',
            'alert_type': 'alert_type',
            'mo': 'production_order__code',
            'process': 'process_name',
            'defect_rate': 'defect_rate',
            'tolerance_limit': 'tolerance_limit',
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('title', 'Tiêu đề', weight=130),
            _col('assignee', 'Tổ / công đoạn / người', weight=150),
            _col('work_task', 'WorkTask', weight=100, default=False),
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('lot', 'Lô', weight=90, default=False),
            _col('pack_date', 'Ngày', weight=90),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            actions=False,
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
            _col('source', 'Nguồn', weight=100, default=False),
            _col('line_count', 'Dòng SP', weight=80, align='end', default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('overall', 'Kế hoạch tổng thể nguồn', weight=140, default=False),
            _col('period', 'Kỳ', weight=120),
            _col('line_count', 'Dòng SP', weight=80, align='end', default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('overall', 'Kế hoạch tổng thể nguồn', weight=140, default=False),
            _col('line_count', 'Dòng NPL', weight=80, align='end', default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('plan', 'Kế hoạch NPL', weight=130, default=False),
            _col('request_date', 'Ngày yêu cầu', weight=100),
            _col('due_date', 'Hạn', weight=90),
            _col('line_count', 'Dòng', weight=70, align='end', default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('pr', 'Yêu cầu mua NPL', weight=140, default=False),
            _col('line_count', 'Số dòng', weight=80, align='end', default=False),
            _col('kv_receipt', 'Phiếu nhập KiotViet', weight=120, default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
        ),
        {
            'code': 'code',
            'supplier': 'supplier_name',
            'pr': 'purchase_request__code',
            'line_count': 'pk',
            'kv_receipt': 'kv_purchase_code',
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
            _col('line_count', 'Dòng', weight=80, align='end', default=False),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('kv_order', 'Đơn KV', weight=110, default=False),
            _col('period', 'Kỳ', weight=120),
            _col('total', 'Tổng', weight=90, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('category', 'Nhóm', weight=110, default=False),
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('disposition', 'Hướng xử lý', weight=120, default=False),
            _col('qty', 'Số lượng', weight=80, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('mo', 'Lệnh sản xuất', weight=150),
            _col('material', 'Nguyên phụ liệu', weight=100, align='end', default=False),
            _col('labor', 'Nhân công', weight=90, align='end', default=False),
            _col('subcontract', 'Gia công', weight=90, align='end', default=False),
            _col('total', 'Tổng', weight=90, align='end'),
            _col('status', 'Trạng thái', weight=100),
            actions=False,
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
            _col('mo', 'Lệnh sản xuất', weight=150),
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
            _col('name', 'Tổ / chuyền', required=True, weight=160),
            _col('team_label', 'Nhãn thống kê', weight=140, default=False),
            _col('capacity', 'NL/ngày', weight=100, align='end'),
            _col('uom', 'ĐVT', weight=70, default=False),
            _col('status', 'Trạng thái', weight=90),
            meta=True,
            actions=False,
        ),
        {
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
            _col('line_count', 'Dòng NPL', weight=80, align='end', default=False),
            _col('step_count', 'Công đoạn', weight=80, align='end', default=False),
            _col('updated_at', 'Cập nhật', weight=110),
            actions=False,
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
            _col('image', 'Ảnh', weight=40, required=True, sortable=False),
            _col('product_name', 'Tên sản phẩm', weight=150, required=True),
            _col('product_code', 'Mã sản phẩm', default=False),
            _col('status', 'Trạng thái', weight=100),
            _col('updated_at', 'Cập nhật', weight=110),
            actions=False,
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
            _col('material', 'Nguyên phụ liệu', weight=100, align='end', default=False),
            _col('labor', 'Nhân công', weight=90, align='end', default=False),
            _col('overhead', 'Phụ phí', weight=90, align='end', default=False),
            _col('total', 'Tổng GT', weight=90, align='end'),
            _col('sell_price', 'Giá bán', weight=90, align='end', default=False),
            _col('margin', 'Biên', weight=80, align='end', default=False),
            actions=False,
        ),
        {
            'product_code': 'product_code',
            'product_name': 'product_name',
        },
    ),
    # IE — thư viện công đoạn / routing (bảng rộng, ẩn-hiện cột như Kho NPL)
    'ie_group': _spec(
        _cols(
            _col('code', 'Mã nhóm', required=True, weight=90, sortable=False),
            _col('name', 'Tên nhóm', required=True, weight=140, sortable=False),
            _col('process_stage', 'Khâu sản xuất', weight=110, sortable=False),
            _col('product_part', 'Sản phẩm cần', weight=110, sortable=False),
            _col('description', 'Mô tả chi tiết', weight=140, default=False, sortable=False),
            _col('is_active', 'Hiệu lực', weight=80, sortable=False),
            _col('data_owner', 'Người lập', weight=110, sortable=False),
            _col('effective_from', 'Ngày hiệu lực', weight=100, sortable=False),
            _col('notes', 'Notes', weight=100, default=False, sortable=False),
            _col('n_ops', 'Số CĐ', weight=70, align='end', sortable=False),
            _col('actions', 'Thao tác', weight=70, required=True, sortable=False, align='end'),
            meta=False,
            actions=False,
        ),
        {'code': 'code', 'name': 'name', 'sort_order': 'sort_order'},
        default_sort='code',
    ),
    'ie_operation': _spec(
        _cols(
            _col('group_code', 'Mã nhóm', weight=80, sortable=False),
            _col('op_code', 'Mã CĐ', required=True, weight=90, sortable=False),
            _col('op_rev', 'Phiên bản', weight=70, sortable=False),
            _col('name_vi', 'Tên công đoạn', required=True, weight=140, sortable=False),
            _col('name_en', 'Tên EN', weight=110, default=False, sortable=False),
            _col('skill_level', 'Bậc CĐ', weight=70, sortable=False),
            _col('time_sec', 'ĐM thời gian (giây)', weight=100, align='end', sortable=False),
            _col('std_capacity', 'ĐM SP/H', weight=80, align='end', sortable=False),
            _col('process_stage', 'Khâu SX', weight=90, sortable=False),
            _col('product_part', 'Cụm chi tiết', weight=100, default=False, sortable=False),
            _col('method_variant', 'Mô tả PP', weight=120, default=False, sortable=False),
            _col('machine_code', 'Mã máy', weight=80, sortable=False),
            _col('stitch_class', 'Nhóm mũi', weight=80, default=False, sortable=False),
            _col('thread_needle', 'Kim/chỉ', weight=80, default=False, sortable=False),
            _col('attachment', 'Cữ/gá', weight=80, default=False, sortable=False),
            _col('smv_basis', 'Đơn vị', weight=70, default=False, sortable=False),
            _col('smv_source', 'Nguồn SMV', weight=90, default=False, sortable=False),
            _col('status', 'Trạng thái', weight=90, sortable=False),
            _col('effective_from', 'Ngày HL', weight=90, default=False, sortable=False),
            _col('effective_to', 'Ngày hết HL', weight=90, default=False, sortable=False),
            _col('ie_owner', 'Người lập', weight=90, default=False, sortable=False),
            _col('approved_by', 'Người duyệt', weight=90, default=False, sortable=False),
            _col('revision_reason', 'Lý do phiên bản', weight=110, default=False, sortable=False),
            _col('notes', 'Notes', weight=100, default=False, sortable=False),
            _col('actions', 'Thao tác', weight=70, required=True, sortable=False, align='end'),
            meta=False,
            actions=False,
        ),
        {'op_code': 'op_code', 'name_vi': 'name_vi', 'status': 'status'},
        default_sort='op_code',
    ),
    'ie_routing': _spec(
        _cols(
            _col('routing_id', 'Mã đơn hàng', required=True, weight=110, sortable=False),
            _col('style_code', 'Mã hàng SP', required=True, weight=100, sortable=False),
            _col('style_name', 'Tên mã hàng', weight=140, sortable=False),
            _col('product_family', 'Nhóm SP', weight=100, default=False, sortable=False),
            _col('routing_rev', 'Phiên bản', weight=70, sortable=False),
            _col('n_lines', 'Công đoạn', weight=80, align='end', sortable=False),
            _col('sum_smv', 'Tổng ĐM (giây)', weight=100, align='end', sortable=False),
            _col('is_active', 'Trạng thái áp dụng', weight=100, sortable=False),
            _col('ie_owner', 'Người lập', weight=90, default=False, sortable=False),
            _col('effective_from', 'Ngày HL', weight=90, default=False, sortable=False),
            _col('approval_status', 'Trạng thái duyệt', weight=110, sortable=False),
            _col('approved_by', 'Người duyệt', weight=90, default=False, sortable=False),
            _col('actions', 'Thao tác', weight=70, required=True, sortable=False, align='end'),
            meta=False,
            actions=False,
        ),
        {'routing_id': 'routing_id', 'style_code': 'style_code', 'routing_rev': 'routing_rev'},
        default_sort='style_code',
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
        'total_col_weight': sum(c['weight'] for c in cols) or 1,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'sx_default_sort_key': spec.get('default_sort') or 'code',
        'sx_list_table_id': f'sx-list-{list_key}',
        'sx_list_storage_key': f'san_xuat_{list_key}_cols_v3',
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
