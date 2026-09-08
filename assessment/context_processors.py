"""Badge menu Đào tạo / Kiểm tra / Việc cần làm — chạy trên mọi request.

Ba con số này chỉ dùng cho badge trên thanh tiêu đề, nên được cache ngắn hạn
theo user (xem ``assessment.portal_widgets.portal_badge_counts``) thay vì tính
lại toàn bộ danh sách nhắc việc mỗi lần tải trang.
"""

_EMPTY = {
    'jp_training_pending_count': 0,
    'jp_assessment_pending_count': 0,
    'jp_portal_todo_count': 0,
}


def portal_learning_menu_badges(request):
    if not request.user.is_authenticated:
        return dict(_EMPTY)

    try:
        from django.db.utils import OperationalError, ProgrammingError

        from assessment.portal_widgets import portal_badge_counts

        counts = portal_badge_counts(request.user)
        return {
            'jp_training_pending_count': counts.get('training', 0),
            'jp_assessment_pending_count': counts.get('assessment', 0),
            'jp_portal_todo_count': counts.get('todo', 0),
        }
    except (ProgrammingError, OperationalError):
        return dict(_EMPTY)
