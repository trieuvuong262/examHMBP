"""Xây dựng ngữ cảnh hỏi đáp theo quyền truy cập của user."""

from django.utils.html import strip_tags

from announcements.models import Announcement
from documents.models import Document, DocumentCategory
from hrm.models import UserGuide
from hrm.module_permissions import MODULE_LABELS, get_user_enabled_modules
from hrm.permissions import get_profile, role_display


def _clip(text: str, limit: int = 1800) -> str:
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + '…'


def build_user_context(user) -> str:
    profile = get_profile(user)
    enabled = sorted(get_user_enabled_modules(user))
    module_labels = [MODULE_LABELS.get(key, key) for key in enabled]

    lines = [
        '=== THÔNG TIN NGƯỜI HỎI (chỉ dùng để xưng hô, không tiết lộ cho người khác) ===',
        f'Họ tên: {profile.full_name if profile else user.get_full_name() or user.username}',
        f'Vai trò: {role_display(user)}',
    ]
    if profile and profile.department:
        lines.append(f'Phòng ban: {profile.department.name}')
    if profile and profile.division:
        lines.append(f'Bộ phận: {profile.division.name}')
    lines.append(f'Module được phép truy cập: {", ".join(module_labels) or "không xác định"}')
    return '\n'.join(lines)


def build_documents_context() -> str:
    categories = DocumentCategory.objects.filter(is_active=True).prefetch_related('documents')
    parts = ['=== TÀI LIỆU NỘI BỘ (công khai trong portal) ===']
    doc_count = 0
    for category in categories:
        active_docs = [d for d in category.documents.all() if d.is_active]
        if not active_docs:
            continue
        parts.append(f'\n## Nhóm: {category.name}')
        if category.description:
            parts.append(_clip(category.description, 300))
        for doc in active_docs[:12]:
            doc_count += 1
            if doc_count > 40:
                break
            parts.append(f'\n### {doc.title}')
            if doc.summary:
                parts.append(f'Tóm tắt: {_clip(doc.summary, 400)}')
            if doc.content_type == Document.TYPE_TEXT and doc.body:
                parts.append(_clip(strip_tags(doc.body), 1200))
            elif doc.content_type == Document.TYPE_PDF:
                parts.append('(Nội dung dạng PDF — xem file trên trang Tài liệu)')
        if doc_count > 40:
            break
    if doc_count == 0:
        parts.append('Chưa có tài liệu nào được xuất bản.')
    return '\n'.join(parts)


def build_guide_context(user) -> str:
    from hrm.module_permissions import MODULE_GUIDE, user_can_access_module

    if not user_can_access_module(user, MODULE_GUIDE):
        return ''
    guide = UserGuide.objects.filter(pk=1).first()
    if not guide or not strip_tags(guide.body or '').strip():
        return ''
    return '\n'.join([
        '=== HƯỚNG DẪN SỬ DỤNG PORTAL ===',
        f'Tiêu đề: {guide.title}',
        _clip(strip_tags(guide.body), 6000),
    ])


def build_announcements_context(user) -> str:
    from hrm.module_permissions import MODULE_ANNOUNCEMENTS, user_can_access_module

    if not user_can_access_module(user, MODULE_ANNOUNCEMENTS):
        return ''
    items = Announcement.objects.filter(is_active=True).order_by('-is_pinned', '-created_at')[:15]
    if not items:
        return ''
    parts = ['=== THÔNG BÁO NỘI BỘ (gần đây) ===']
    for item in items:
        parts.append(f'\n- {item.title}')
        if item.summary:
            parts.append(f'  {_clip(item.summary, 250)}')
    return '\n'.join(parts)


def build_portal_knowledge(user) -> str:
    sections = [
        build_user_context(user),
        build_documents_context(),
        build_guide_context(user),
        build_announcements_context(user),
    ]
    return '\n\n'.join(part for part in sections if part.strip())
