def unread_announcements(request):
    """Số thông báo chưa xác nhận đọc — chạy trên mọi request nên phải rẻ.

    Trước đây dùng ``announcement__in=active_qs`` (subquery) khiến Postgres quét
    tuần tự bảng thông báo mỗi lần. Nay lấy id thông báo đang bật một lần rồi
    đếm bản ghi đã đọc theo danh sách id đó, và memo hoá theo request.
    """
    if not request.user.is_authenticated:
        return {'unread_announcements_count': 0}

    from hrm.request_cache import get_or_set, user_key

    return {
        'unread_announcements_count': get_or_set(
            user_key('unread_announcements', request.user),
            lambda: _unread_count(request.user),
        ),
    }


def _unread_count(user) -> int:
    from django.db.utils import OperationalError, ProgrammingError

    from .models import Announcement, AnnouncementRead

    try:
        active_ids = list(
            Announcement.objects.filter(is_active=True).values_list('id', flat=True)
        )
        if not active_ids:
            return 0
        read_count = AnnouncementRead.objects.filter(
            user=user,
            announcement_id__in=active_ids,
        ).count()
        return max(len(active_ids) - read_count, 0)
    except (ProgrammingError, OperationalError):
        return 0
