"""Tự động gán thứ tự hiển thị (sort_order) khi thêm danh mục mới."""

from django.db.models import Max, QuerySet


def next_sort_order(queryset: QuerySet) -> int:
    """Số tiếp theo trong cùng nhóm (max + 1), bắt đầu từ 0 nếu chưa có bản ghi."""
    current = queryset.aggregate(m=Max('sort_order'))['m']
    if current is None:
        return 0
    return int(current) + 1


def resolve_sort_order_on_create(
    *,
    posted: int,
    field_initial,
    scope_changed: bool,
    queryset: QuerySet,
) -> int:
    """Giữ số user tự sửa; còn lại gán max+1 trong queryset (kể cả đổi phòng/bộ phận)."""
    if scope_changed or field_initial is None or posted == field_initial:
        return next_sort_order(queryset)
    return int(posted)
