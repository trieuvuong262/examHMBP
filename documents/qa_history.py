"""Lưu trữ và truy vấn lịch sử hỏi đáp AI."""

from django.contrib.auth.models import User

from .models import LibraryQAChatMessage

QA_HISTORY_CONTEXT_LIMIT = 12
QA_HISTORY_DISPLAY_LIMIT = 500


def get_user_qa_history(user, *, limit: int = QA_HISTORY_CONTEXT_LIMIT) -> list[dict]:
    qs = LibraryQAChatMessage.objects.filter(user=user).order_by('-created_at')
    if limit:
        qs = qs[:limit]
    messages = list(qs)
    messages.reverse()
    return [{'role': m.role, 'text': m.text} for m in messages]


def get_user_qa_history_for_display(user) -> list[dict]:
    return get_user_qa_history(user, limit=QA_HISTORY_DISPLAY_LIMIT)


def save_qa_turn(user, question: str, answer: str) -> None:
    LibraryQAChatMessage.objects.create(
        user=user,
        role=LibraryQAChatMessage.ROLE_USER,
        text=question[:8000],
    )
    LibraryQAChatMessage.objects.create(
        user=user,
        role=LibraryQAChatMessage.ROLE_MODEL,
        text=answer[:8000],
    )


def clear_user_qa_history(user_id: int) -> int:
    deleted, _ = LibraryQAChatMessage.objects.filter(user_id=user_id).delete()
    return deleted


def users_with_qa_history():
    return (
        User.objects.filter(library_qa_messages__isnull=False)
        .distinct()
        .select_related('profile')
        .order_by('profile__full_name', 'username')
    )
