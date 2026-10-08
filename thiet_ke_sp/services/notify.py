"""Thông báo trong portal — mỗi thông báo mở đúng hồ sơ."""

from __future__ import annotations

from thiet_ke_sp.models import Notification, ProductDevelopment

KIND_TASK = 'task'
KIND_APPROVAL_REQUEST = 'approval_request'
KIND_REVISION = 'revision'
KIND_DUE_SOON = 'due_soon'
KIND_OVERDUE = 'overdue'
KIND_APPROVED = 'approved'
KIND_HANDOVER = 'handover'
KIND_COMMENT = 'comment'
KIND_INFO = 'info'

KIND_ICONS = {
    KIND_TASK: 'bi-person-check',
    KIND_APPROVAL_REQUEST: 'bi-check2-circle',
    KIND_REVISION: 'bi-arrow-counterclockwise',
    KIND_DUE_SOON: 'bi-hourglass-split',
    KIND_OVERDUE: 'bi-exclamation-triangle-fill',
    KIND_APPROVED: 'bi-patch-check-fill',
    KIND_HANDOVER: 'bi-box-arrow-right',
    KIND_COMMENT: 'bi-chat-dots',
    KIND_INFO: 'bi-info-circle',
}


def notify(user, dossier: ProductDevelopment | None, kind: str, title: str, body: str = '', *, actor=None):
    if user is None or not getattr(user, 'is_active', True):
        return None
    if actor is not None and getattr(actor, 'pk', None) == user.pk:
        return None
    url = dossier.get_absolute_url() if dossier else ''
    note = Notification.objects.create(
        user=user, dossier=dossier, kind=kind, title=title[:255], body=body, url=url,
    )
    _invalidate_badges(user)
    return note


def notify_many(users, dossier, kind, title, body='', *, actor=None):
    seen = set()
    for user in users:
        if user is None or user.pk in seen:
            continue
        seen.add(user.pk)
        notify(user, dossier, kind, title, body, actor=actor)


def _invalidate_badges(user) -> None:
    try:
        from assessment.portal_widgets import invalidate_portal_badges
    except ImportError:
        return
    invalidate_portal_badges(user)
