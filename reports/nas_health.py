"""Kiểm tra nhanh tình trạng thư mục lưu trữ NAS cho module Báo cáo.

Dùng để đánh dấu NAS lỗi khi ghi file thất bại và phục vụ fallback lưu tạm trên VPS.
Không hiển thị cảnh báo trên giao diện người dùng.

QUAN TRỌNG — vì sao KHÔNG kiểm tra bằng cách đọc mount ``/mnt/nas-portal``:
Khi NAS mất kết nối, mount rclone/FUSE bị treo, mọi thao tác I/O (``os.access``,
``listdir``, ``ls``...) rơi vào trạng thái **D (uninterruptible sleep)** — không thể
kill kể cả bằng ``subprocess timeout`` hay ``gunicorn --timeout``. Chỉ cần một request
chạm mount là worker gunicorn kẹt cứng, cạn worker → sập toàn site.
Vì vậy probe kiểm tra NAS **qua mạng bằng rclone CLI** (tiến trình network bình
thường, timeout kill được), tuyệt đối không chạm vào mount FUSE.

Probe thực tế nằm ở ``nas_storage.nas_mount_health`` để dùng chung cho cả portal
(duyệt thư mục NAS, thông báo, hồ sơ thiết kế...). Module này giữ lại tên hàm cũ
cho module Báo cáo.
"""

from __future__ import annotations

from nas_storage.nas_mount_health import mark_remote_unavailable, remote_reachable


def report_storage_available(*, use_cache: bool = True) -> bool:
    """True nếu NAS đang sẵn sàng ghi đính kèm báo cáo (kết quả cache ngắn)."""
    return remote_reachable(use_cache=use_cache)


def mark_storage_unavailable() -> None:
    """Đánh dấu NAS lỗi ngay (gọi khi một lần ghi file thất bại)."""
    mark_remote_unavailable()
