import re

from django.contrib.auth.models import User

MENTION_PATTERN = re.compile(r'@([a-zA-Z0-9_\.]+)')


def parse_mentioned_usernames(text: str) -> list[str]:
    return list(dict.fromkeys(MENTION_PATTERN.findall(text or '')))


def resolve_project_mentions(text: str, allowed_users) -> tuple[list[User], str]:
    """Lọc @username — chỉ giữ user trong allowed_users (members dự án)."""
    allowed_map = {u.username.lower(): u for u in allowed_users}
    mentioned = []
    for raw in parse_mentioned_usernames(text):
        user = allowed_map.get(raw.lower())
        if user and user not in mentioned:
            mentioned.append(user)
    return mentioned, text


def render_comment_body_html(body: str) -> str:
    """Highlight @username trong comment (escape HTML cơ bản)."""
    from django.utils.html import escape

    escaped = escape(body)
    return MENTION_PATTERN.sub(
        r'<span class="jp-project-mention">@\1</span>',
        escaped,
    )


def unlock_dependent_steps(completed_task):
    """Mở các bước phụ thuộc khi bước trước hoàn thành."""
    from .models import WorkTask

    if not completed_task.project_id:
        return []
    unlocked = []
    for child in WorkTask.objects.filter(
        project_id=completed_task.project_id,
        depends_on_id=completed_task.pk,
        status=WorkTask.STATUS_BLOCKED,
    ):
        child.status = WorkTask.STATUS_PENDING_ACK
        child.save(update_fields=['status', 'updated_at'])
        unlocked.append(child)
    return unlocked


def initial_step_status(depends_on_task):
    from .models import WorkTask

    if depends_on_task is None:
        return WorkTask.STATUS_PENDING_ACK
    if depends_on_task.status == WorkTask.STATUS_COMPLETED:
        return WorkTask.STATUS_PENDING_ACK
    return WorkTask.STATUS_BLOCKED
