"""Badge menu Đào tạo / Kiểm tra — không dùng web push."""


def portal_learning_menu_badges(request):
    if not request.user.is_authenticated:
        return {
            'jp_training_pending_count': 0,
            'jp_assessment_pending_count': 0,
        }

    try:
        from django.db.utils import OperationalError, ProgrammingError

        from assessment.portal_widgets import (
            get_assessment_pending_count,
            get_training_pending_count,
        )

        user = request.user
        return {
            'jp_training_pending_count': get_training_pending_count(user),
            'jp_assessment_pending_count': get_assessment_pending_count(user),
        }
    except (ProgrammingError, OperationalError):
        return {
            'jp_training_pending_count': 0,
            'jp_assessment_pending_count': 0,
        }
