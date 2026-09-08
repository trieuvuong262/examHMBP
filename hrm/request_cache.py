"""Cache trong phạm vi một request (memo hoá) cho dữ liệu phân quyền & thiết lập.

Vấn đề: hệ thống phân quyền được gọi rất nhiều lần trong một request —
sidebar có 83 lần ``{% jp_can_menu %}``, context processor kiểm tra ~35 module,
middleware kiểm tra module + menu. Mỗi lần lại truy vấn lại
``PermissionGroup`` / ``Department`` / ``DepartmentMenuPermission`` /
``ProfileConcurrentPosition``, dẫn tới hơn 100 truy vấn trùng nhau mỗi request.

Giải pháp: memo hoá theo request. Điểm quan trọng:

  * Cache **chỉ bật cho request đọc** (GET/HEAD/OPTIONS). Request ghi
    (POST/PUT/PATCH/DELETE) không dùng cache, nên sửa quyền rồi đọc lại ngay
    trong cùng request vẫn thấy giá trị mới.
  * Ngoài phạm vi request (management command, celery, test gọi hàm trực tiếp)
    cache tắt hoàn toàn → giữ đúng hành vi cũ.
  * Lưu bằng ``threading.local`` nên an toàn với gunicorn sync worker và cả
    worker đa luồng.
"""

from __future__ import annotations

import threading

_state = threading.local()

SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


def begin(enabled: bool = True) -> None:
    """Mở phạm vi cache cho request hiện tại."""
    _state.store = {} if enabled else None


def end() -> None:
    """Đóng phạm vi cache — luôn gọi trong finally để không rò rỉ giữa request."""
    _state.store = None


def is_active() -> bool:
    return getattr(_state, 'store', None) is not None


def get_or_set(key, producer):
    """Trả giá trị đã memo hoá; nếu chưa có phạm vi cache thì gọi thẳng producer."""
    store = getattr(_state, 'store', None)
    if store is None:
        return producer()
    if key in store:
        return store[key]
    value = producer()
    store[key] = value
    return value


def invalidate(prefix: str | None = None) -> None:
    """Xoá cache (toàn bộ hoặc theo tiền tố khoá) khi dữ liệu vừa bị sửa."""
    store = getattr(_state, 'store', None)
    if store is None:
        return
    if prefix is None:
        store.clear()
        return
    for key in [k for k in store if isinstance(k, tuple) and k and k[0] == prefix]:
        store.pop(key, None)


def user_key(prefix: str, user, *extra):
    """Khoá cache gắn với user — dùng pk để không phụ thuộc instance."""
    pk = getattr(user, 'pk', None)
    return (prefix, pk, *extra)


class RequestCacheMiddleware:
    """Bật/tắt phạm vi cache theo từng request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        begin(enabled=request.method in SAFE_METHODS)
        try:
            return self.get_response(request)
        finally:
            end()
