"""Nhật ký thao tác kế hoạch sản xuất.

Ghi lại ai làm gì trên KHTT / KHCT / KHNVL / YCM / DMH để truy vết khi kế hoạch
bị thay đổi giữa kỳ (yêu cầu P4 — đóng vòng phản hồi).

Hàm ``log_plan_action`` cố tình *không* raise: nhật ký không được phép làm gãy
nghiệp vụ chính. Mọi lỗi ghi log bị bỏ qua im lặng.
"""

from __future__ import annotations

from san_xuat.hub_models import SxPlanAuditLog

# Ánh xạ tên model → nhãn tiếng Việt hiển thị trên danh sách nhật ký
OBJECT_LABELS = {
    'SxOverallPlan': 'Kế hoạch tổng thể',
    'SxDetailPlan': 'Kế hoạch chi tiết',
    'SxMaterialPlan': 'Kế hoạch NPL',
    'SxNplPurchaseRequest': 'Yêu cầu mua NPL',
    'SxPurchaseOrder': 'Đơn mua hàng',
    'SxProductStockPolicy': 'Chính sách tồn TP',
    'SxSalesOrder': 'Đơn đặt hàng',
    'SxSalesOrderLine': 'Dòng đơn đặt hàng',
}


def object_label(object_type: str) -> str:
    return OBJECT_LABELS.get(object_type, object_type or '—')


def log_plan_action(
    *,
    action: str,
    obj=None,
    object_type: str = '',
    object_id=None,
    object_code: str = '',
    summary: str = '',
    changes: dict | None = None,
    user=None,
) -> SxPlanAuditLog | None:
    """Ghi một dòng nhật ký kế hoạch. Trả None nếu ghi không thành công."""
    try:
        if obj is not None:
            object_type = object_type or obj.__class__.__name__
            object_id = object_id if object_id is not None else obj.pk
            object_code = object_code or getattr(obj, 'code', '') or ''
        username = ''
        user_obj = user if getattr(user, 'pk', None) else None
        if user_obj is not None:
            username = getattr(user_obj, 'username', '') or ''
        return SxPlanAuditLog.objects.create(
            action=action,
            object_type=object_type or '',
            object_id=str(object_id or ''),
            object_code=(object_code or '')[:100],
            summary=(summary or '')[:500],
            changes=changes or {},
            user=user_obj,
            username=username[:150],
        )
    except Exception:  # pragma: no cover - nhật ký không được làm gãy nghiệp vụ
        return None


def plan_audit_qs(*, object_type: str = '', action: str = '', search: str = ''):
    """Queryset nhật ký đã lọc — dùng cho màn hình danh sách."""
    qs = SxPlanAuditLog.objects.select_related('user').all()
    if object_type:
        qs = qs.filter(object_type=object_type)
    if action:
        qs = qs.filter(action=action)
    term = (search or '').strip()
    if term:
        from django.db.models import Q

        qs = qs.filter(
            Q(object_code__icontains=term)
            | Q(summary__icontains=term)
            | Q(username__icontains=term)
        )
    return qs
