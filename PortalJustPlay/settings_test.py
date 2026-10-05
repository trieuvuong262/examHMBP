"""Settings dùng cho chạy test cục bộ — dựng schema trực tiếp từ models,
bỏ qua các data-migration lịch sử (tránh lỗi migration tiền tồn tại không
liên quan). Chỉ dùng cho `manage.py test`.
"""

from PortalJustPlay.settings import *  # noqa: F401,F403


class _DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()
