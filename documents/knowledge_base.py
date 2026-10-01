"""Xây dựng ngữ cảnh hỏi đáp theo quyền truy cập của user."""

import logging

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.html import strip_tags

from announcements.models import Announcement
from documents.models import DocumentCategory
from hrm.models import UserGuide
from hrm.module_permissions import ALL_MODULE_KEYS, MODULE_LABELS, user_can_access_module
from hrm.permissions import get_profile, role_display

logger = logging.getLogger(__name__)


def _clip(text: str, limit: int = 1800) -> str:
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + '…'


def _absolute_url(path: str, request=None) -> str:
    if not path.startswith('/'):
        path = f'/{path}'
    if request is not None:
        try:
            return request.build_absolute_uri(path)
        except Exception:
            pass
    scheme = 'https' if getattr(settings, 'USE_HTTPS', False) else 'http'
    domain = getattr(settings, 'PORTAL_DOMAIN', 'localhost') or 'localhost'
    return f'{scheme}://{domain}{path}'


def _document_url(category, document, request=None) -> str:
    try:
        path = reverse(
            'documents:browse_document',
            kwargs={'category_slug': category.slug, 'doc_slug': document.slug},
        )
    except NoReverseMatch:
        # Slug có dấu (slugify allow_unicode) không khớp pattern URL ASCII.
        path = reverse('documents:browse')
    return _absolute_url(path, request)


def _accessible_module_labels(user) -> list[str]:
    """Module user thực sự mở được (phòng ban + nhóm quyền), không chỉ cấu hình phòng ban."""
    keys = sorted(k for k in ALL_MODULE_KEYS if user_can_access_module(user, k))
    return [MODULE_LABELS.get(k, k) for k in keys]


def build_user_context(user) -> str:
    profile = get_profile(user)
    module_labels = _accessible_module_labels(user)

    lines = [
        '=== THÔNG TIN NGƯỜI HỎI (chỉ dùng để xưng hô, không tiết lộ cho người khác) ===',
        f'Họ tên: {profile.full_name if profile else user.get_full_name() or user.username}',
        f'Vai trò: {role_display(user)}',
    ]
    if profile and profile.department:
        lines.append(f'Phòng ban: {profile.department.name}')
    if profile and profile.division:
        lines.append(f'Bộ phận: {profile.division.name}')
    lines.append(
        'Module được phép truy cập (CHỈ trả lời đúng danh sách này — không thêm module khác): '
        f'{", ".join(module_labels) or "không có"}'
    )
    return '\n'.join(lines)


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
        _clip(strip_tags(guide.body), 2000),
    ])


def build_announcements_context(user, request=None) -> str:
    from hrm.module_permissions import MODULE_ANNOUNCEMENTS, user_can_access_module

    if not user_can_access_module(user, MODULE_ANNOUNCEMENTS):
        return ''
    items = Announcement.objects.filter(is_active=True).order_by('-is_pinned', '-created_at')[:5]
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


PASSAGE_CHAR_BUDGET = 28_000
DOC_INDEX_LIMIT = 200


def build_menu_map_context(user) -> str:
    """Menu con user thực sự mở được — để AI chỉ đường đúng tên trên sidebar."""
    from hrm.menu_permissions import user_can_access_menu
    from hrm.module_permissions import is_portal_module_visible
    from hrm.submenu_registry import get_module_submenus

    lines = ['=== SƠ ĐỒ MENU NGƯỜI HỎI ĐƯỢC DÙNG (sidebar bên trái) ===']
    for key in sorted(ALL_MODULE_KEYS, key=lambda k: MODULE_LABELS.get(k, k)):
        if not is_portal_module_visible(key) or not user_can_access_module(user, key):
            continue
        menus = []
        for menu in get_module_submenus(key):
            try:
                if user_can_access_menu(user, key, menu['key']):
                    menus.append(menu['label'])
            except Exception:
                continue
        label = MODULE_LABELS.get(key, key)
        lines.append(f'- {label}' + (f': {", ".join(menus)}' if menus else ''))
    return '\n'.join(lines) if len(lines) > 1 else ''


def _active_documents(request=None) -> list[tuple]:
    out = []
    categories = DocumentCategory.objects.filter(is_active=True).prefetch_related('documents')
    for category in categories:
        for doc in category.documents.all():
            if doc.is_active:
                out.append((doc, category.name, _document_url(category, doc, request)))
    return out


def build_documents_index_context(docs, request=None) -> str:
    library_url = _absolute_url(reverse('documents:browse'), request)
    parts = [
        '=== DANH MỤC TÀI LIỆU NỘI BỘ ===',
        f'Trang Thư viện: {library_url}',
    ]
    if not docs:
        parts.append('Chưa có tài liệu nào được xuất bản.')
    for doc, category_name, url in docs[:DOC_INDEX_LIMIT]:
        line = f'• {doc.title} ({category_name}) — {url}'
        if doc.summary:
            line += f' — {_clip(doc.summary, 140)}'
        parts.append(line)
    return '\n'.join(parts)


def build_retrieved_passages_context(user, docs, request=None, query: str = '') -> str:
    from documents import qa_retrieval

    from hrm.module_permissions import MODULE_GUIDE

    passages = qa_retrieval.document_passages(docs)
    if request is not None and user_can_access_module(user, MODULE_GUIDE):
        try:
            passages += qa_retrieval.guide_passages(request, _absolute_url(reverse('user_guide'), request))
        except Exception:
            logger.warning('QA guide passages failed', exc_info=True)

    picked = qa_retrieval.rank_passages(passages, query, char_budget=PASSAGE_CHAR_BUDGET)
    if not picked:
        return ''
    parts = [
        '=== TRÍCH ĐOẠN LIÊN QUAN CÂU HỎI (nguồn chính để trả lời — trích từ nội dung thật) ===',
    ]
    for i, p in enumerate(picked, 1):
        parts.append(f'\n[Nguồn {i}] {p.source}\nLink: {p.url}\n{p.text}')
    return '\n'.join(parts)


def build_portal_knowledge(user, request=None, question: str = '', retrieval_query: str = '') -> str:
    """Ngữ cảnh cho trợ lý QA — quyền user, menu, danh mục tài liệu và trích đoạn liên quan."""
    docs = _active_documents(request)
    sections = [
        build_user_context(user),
        build_menu_map_context(user),
        build_retrieved_passages_context(user, docs, request, query=retrieval_query or question),
        build_documents_index_context(docs, request),
        build_announcements_context(user, request),
    ]
    if request is None:
        sections.append(build_guide_context(user, request))
    return '\n\n'.join(part for part in sections if part and part.strip())
