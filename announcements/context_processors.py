def unread_announcements(request):
    if not request.user.is_authenticated:
        return {'unread_announcements_count': 0}

    try:
        from django.db.utils import ProgrammingError, OperationalError
        from .models import Announcement, AnnouncementRead

        active_qs = Announcement.objects.filter(is_active=True)
        active_count = active_qs.count()
        read_count = AnnouncementRead.objects.filter(
            user=request.user,
            announcement__in=active_qs,
        ).count()

        return {
            'unread_announcements_count': max(active_count - read_count, 0),
        }
    except (ProgrammingError, OperationalError):
        return {'unread_announcements_count': 0}
