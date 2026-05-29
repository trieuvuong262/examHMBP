"""Xây dựng ngữ cảnh hỏi đáp theo quyền truy cập của user."""

from django.conf import settings
from django.urls import reverse
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


def _absolute_url(path: str, request=None) -> str:
    if request is not None:
        return request.build_absolute_uri(path)
    scheme = 'https' if getattr(settings, 'USE_HTTPS', False) else 'http'
    domain = getattr(settings, 'PORTAL_DOMAIN', 'localhost') or 'localhost'
    if not path.startswith('/'):
        path = f'/{path}'
    return f'{scheme}://{domain}{path}'


def _document_url(category, document, request=None) -> str:
    path = reverse(
        'documents:browse_document',
        kwargs={'category_slug': category.slug, 'doc_slug': document.slug},
    )
    return _absolute_url(path, request)


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


def build_documents_context(request=None) -> str:
    categories = DocumentCategory.objects.filter(is_active=True).prefetch_related('documents')
    library_url = _absolute_url(reverse('documents:browse'), request)
    qa_url = _absolute_url(reverse('documents:qa'), request)

    parts = [
        '=== TÀI LIỆU NỘI BỘ (công khai trong portal) ===',
        f'Trang Thư viện — Tài liệu: {library_url}',
        f'Trang Hỏi đáp: {qa_url}',
        'Mỗi tài liệu bên dưới có Link URL — khi user hỏi, hãy đưa link đầy đủ để mở nhanh.',
    ]
    doc_count = 0
    for category in categories:
        active_docs = [d for d in category.documents.all() if d.is_active]
        if not active_docs:
            continue
        category_url = _absolute_url(
            reverse('documents:browse_category', kwargs={'category_slug': category.slug}),
            request,
        )
        parts.append(f'\n## Nhóm: {category.name}')
        parts.append(f'Link nhóm: {category_url}')
        if category.description:
            parts.append(_clip(category.description, 300))
        for doc in active_docs[:12]:
            doc_count += 1
            if doc_count > 40:
                break
            parts.append(f'\n### {doc.title}')
            parts.append(f'Link: {_document_url(category, doc, request)}')
            if doc.summary:
                parts.append(f'Tóm tắt: {_clip(doc.summary, 400)}')
            if doc.content_type == Document.TYPE_TEXT and doc.body:
                parts.append(_clip(strip_tags(doc.body), 1200))
            elif doc.content_type == Document.TYPE_PDF:
                parts.append('(Nội dung dạng PDF — mở link trên để xem/tải file)')
        if doc_count > 40:
            break
    if doc_count == 0:
        parts.append('Chưa có tài liệu nào được xuất bản.')
    return '\n'.join(parts)


def build_documents_index(request=None) -> list[dict]:
    """Chỉ mục tài liệu gọn — dùng cho gợi ý câu hỏi thông minh."""
    categories = DocumentCategory.objects.filter(is_active=True).prefetch_related('documents')
    index: list[dict] = []
    for category in categories:
        for doc in category.documents.all():
            if not doc.is_active:
                continue
            index.append({
                'id': doc.pk,
                'title': doc.title,
                'slug': doc.slug,
                'category': category.name,
                'category_slug': category.slug,
                'summary': _clip(doc.summary, 120) if doc.summary else '',
                'url': _document_url(category, doc, request),
            })
    return index


def build_guide_context(user, request=None) -> str:
    from hrm.module_permissions import MODULE_GUIDE, user_can_access_module

    if not user_can_access_module(user, MODULE_GUIDE):
        return ''
    guide = UserGuide.objects.filter(pk=1).first()
    if not guide or not strip_tags(guide.body or '').strip():
        return ''
    guide_url = _absolute_url(reverse('user_guide'), request)
    return '\n'.join([
        '=== HƯỚNG DẪN SỬ DỤNG PORTAL ===',
        f'Tiêu đề: {guide.title}',
        f'Link: {guide_url}',
        _clip(strip_tags(guide.body), 6000),
    ])


def build_announcements_context(user, request=None) -> str:
    from hrm.module_permissions import MODULE_ANNOUNCEMENTS, user_can_access_module

    if not user_can_access_module(user, MODULE_ANNOUNCEMENTS):
        return ''
    items = Announcement.objects.filter(is_active=True).order_by('-is_pinned', '-created_at')[:15]
    if not items:
        return ''
    list_url = _absolute_url(reverse('announcements:list'), request)
    parts = [
        '=== THÔNG BÁO NỘI BỘ (gần đây) ===',
        f'Trang danh sách thông báo: {list_url}',
    ]
    for item in items:
        detail_url = _absolute_url(reverse('announcements:detail', kwargs={'pk': item.pk}), request)
        parts.append(f'\n- {item.title}')
        parts.append(f'  Link: {detail_url}')
        if item.summary:
            parts.append(f'  {_clip(item.summary, 250)}')
    return '\n'.join(parts)


def build_portal_knowledge(user, request=None) -> str:
    sections = [
        build_user_context(user),
        build_documents_context(request),
        build_guide_context(user, request),
        build_announcements_context(user, request),
    ]
    return '\n\n'.join(part for part in sections if part.strip())
