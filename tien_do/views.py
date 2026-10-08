import logging
import mimetypes
import os

from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST

from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from assessment.decorators import module_perm_required

from hrm.module_permissions import (
    MODULE_TIEN_DO,
    user_can_access_module,
    user_can_create_module,
    user_can_delete_module,
    user_can_update_module,
)
from hrm.permissions import get_profile
from kpi.services.inline_images import actual_html_for_edit, sanitize_actual_html
from reports.daily_inline_images import (
    inline_image_exists,
    is_inline_image_relpath,
    open_inline_image,
    save_inline_image,
)

from . import importing as tien_do_importing
from .models import TienDoFeedback, TienDoItem

logger = logging.getLogger(__name__)

PLATFORM_LABELS = dict(TienDoItem.PLATFORM_CHOICES)

_IMAGE_TYPES = {
    'image/jpeg', 'image/jpg', 'image/pjpeg', 'image/png', 'image/x-png',
    'image/gif', 'image/webp', 'image/bmp', 'image/x-ms-bmp',
}
_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
_IMAGE_EXT_BY_TYPE = {
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/pjpeg': '.jpg',
    'image/png': '.png',
    'image/x-png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/x-ms-bmp': '.bmp',
}
_IMAGE_MAX_BYTES = 5 * 1024 * 1024


def _can_edit_it_columns(user):
    """Cột IT (Tính năng / Mô tả / User flow): dành cho người có quyền Thêm hoặc Xóa."""
    return user_can_create_module(user, MODULE_TIEN_DO) or user_can_delete_module(user, MODULE_TIEN_DO)


def _can_edit_tester_columns(user):
    """Feedback / Ghi chú: dành cho người có quyền Sửa."""
    return user_can_update_module(user, MODULE_TIEN_DO)


def _perm_context(user):
    can_edit_it = _can_edit_it_columns(user)
    can_edit_tester = _can_edit_tester_columns(user)
    return {
        'can_create': user_can_create_module(user, MODULE_TIEN_DO),
        'can_update': user_can_update_module(user, MODULE_TIEN_DO),
        'can_delete': user_can_delete_module(user, MODULE_TIEN_DO),
        'can_view': user_can_access_module(user, MODULE_TIEN_DO),
        'can_edit_it': can_edit_it,
        'can_edit_tester': can_edit_tester,
        'can_upload_image': can_edit_it or can_edit_tester,
    }


def _platform_or_404(platform):
    if platform not in PLATFORM_LABELS:
        raise Http404
    return platform


def _user_label(user):
    if not user:
        return '—'
    profile = get_profile(user)
    if profile and getattr(profile, 'full_name', ''):
        return profile.full_name
    return user.get_full_name() or user.username


def _initials(label):
    """2 chữ cái đầu cho avatar: 'Trần Nhân Đức' → 'TĐ'."""
    words = [w for w in (label or '').split() if w and w != '—']
    if not words:
        return '?'
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()


def _avatar_url(user):
    """URL ảnh đại diện nhân viên (Profile.avatar); rỗng nếu chưa có ảnh."""
    profile = get_profile(user) if user else None
    avatar = getattr(profile, 'avatar', None) if profile else None
    if not avatar:
        return ''
    try:
        return avatar.url or ''
    except (ValueError, OSError):
        return ''


def _feedback_payload(entry):
    author_label = _user_label(entry.author)
    return {
        'id': entry.pk,
        'feedback_html': actual_html_for_edit(entry.feedback),
        'note_html': actual_html_for_edit(entry.note),
        'author_label': author_label,
        'author_initials': _initials(author_label),
        'author_avatar': _avatar_url(entry.author),
        'created_at': timezone.localtime(entry.created_at),
    }


def _it_field(item, column, can_edit_it):
    return {
        'column': column,
        'label': TienDoItem.COLUMN_LABELS[column],
        'is_rich': column in TienDoItem.RICH_COLUMNS,
        'can_edit': can_edit_it,
        'html': actual_html_for_edit(getattr(item, column)),
    }


def _build_rows(items, *, can_edit_it):
    """Mỗi dòng tiến độ → một card: Tính năng (tiêu đề), Mô tả + User flow, luồng Feedback."""
    rows = []
    for item in items:
        entries = [_feedback_payload(e) for e in item.feedbacks.all()]
        rows.append({
            'item': item,
            'feature': _it_field(item, 'feature', can_edit_it),
            'fields': [_it_field(item, col, can_edit_it) for col in TienDoItem.RICH_COLUMNS],
            'entries': entries,
            'updated_at': timezone.localtime(item.updated_at),
        })
    return rows


def _board_queryset(platform, search_query):
    qs = TienDoItem.objects.filter(platform=platform).prefetch_related(
        Prefetch(
            'feedbacks',
            queryset=TienDoFeedback.objects.select_related('author', 'author__profile'),
        )
    )
    return apply_term_search(qs, search_query, 'feature__icontains', 'description__icontains')


def _export_records(items):
    """Mỗi dòng tiến độ một STT; mỗi feedback một hàng Excel."""
    records = []
    for index, item in enumerate(items, start=1):
        base = {
            'stt': index,
            'feature': tien_do_importing.html_to_plain(item.feature),
            'description': tien_do_importing.html_to_plain(item.description),
            'user_flow': tien_do_importing.html_to_plain(item.user_flow),
            'updated_at': timezone.localtime(item.updated_at).strftime('%d/%m/%Y %H:%M'),
        }
        feedbacks = list(item.feedbacks.all())
        if not feedbacks:
            records.append(base)
            continue
        for entry in feedbacks:
            records.append({
                **base,
                'author': _user_label(entry.author),
                'feedback_at': timezone.localtime(entry.created_at).strftime('%d/%m/%Y %H:%M'),
                'feedback': tien_do_importing.html_to_plain(entry.feedback),
                'note': tien_do_importing.html_to_plain(entry.note),
            })
    return records


def _render_board(request, platform):
    search_query = get_search_query(request)
    qs = _board_queryset(platform, search_query)
    page_obj, query_string = paginate_queryset(request, qs)

    perms = _perm_context(request.user)
    context = {
        'platform': platform,
        'platform_label': PLATFORM_LABELS[platform],
        'rows': _build_rows(page_obj.object_list, can_edit_it=perms['can_edit_it']),
        'current_user_label': _user_label(request.user),
        'current_user_initials': _initials(_user_label(request.user)),
        'current_user_avatar': _avatar_url(request.user),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'image_upload_url': reverse('tien_do:item_image_upload'),
        **perms,
    }
    return render(request, 'tien_do/board.html', context)


@module_perm_required(MODULE_TIEN_DO, 'view')
def board_portal(request):
    return _render_board(request, TienDoItem.PLATFORM_PORTAL)


@module_perm_required(MODULE_TIEN_DO, 'view')
def board_wholesale_retail(request):
    return _render_board(request, TienDoItem.PLATFORM_WHOLESALE_RETAIL)


@module_perm_required(MODULE_TIEN_DO, 'view')
def board_wholesale_retail_export(request):
    """Xuất Excel toàn bộ dòng Website sỉ/lẻ (theo ô tìm kiếm, không chỉ trang hiện tại)."""
    search_query = get_search_query(request)
    items = _board_queryset(TienDoItem.PLATFORM_WHOLESALE_RETAIL, search_query)
    response = HttpResponse(
        tien_do_importing.build_board_export_xlsx(_export_records(items)),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="tien_do_website_si_le_{timezone.localdate():%Y%m%d}.xlsx"'
    )
    return response


@module_perm_required(MODULE_TIEN_DO, 'create')
@require_POST
def item_create(request, platform):
    _platform_or_404(platform)
    TienDoItem.objects.create(platform=platform, created_by=request.user)
    messages.success(request, 'Đã thêm dòng tiến độ mới.')
    if platform == TienDoItem.PLATFORM_WHOLESALE_RETAIL:
        return redirect('tien_do:wholesale_retail')
    return redirect('tien_do:portal')


def _board_redirect(platform):
    if platform == TienDoItem.PLATFORM_WHOLESALE_RETAIL:
        return redirect('tien_do:wholesale_retail')
    return redirect('tien_do:portal')


@module_perm_required(MODULE_TIEN_DO, 'create')
@require_POST
def item_import(request, platform):
    """Import Tính năng / Mô tả / User flow từ Excel — chỉ người có quyền Thêm."""
    _platform_or_404(platform)
    upload = request.FILES.get('file')
    if not upload:
        messages.error(request, 'Chưa chọn file Excel.')
        return _board_redirect(platform)
    if not (upload.name or '').lower().endswith(('.xlsx', '.xlsm')):
        messages.error(request, 'Chỉ nhận file .xlsx.')
        return _board_redirect(platform)
    if upload.size > tien_do_importing.MAX_FILE_BYTES:
        messages.error(request, 'File quá lớn (tối đa 5MB).')
        return _board_redirect(platform)

    try:
        rows = tien_do_importing.parse_workbook(upload)
    except tien_do_importing.TienDoImportError as exc:
        messages.error(request, str(exc))
        return _board_redirect(platform)

    with transaction.atomic():
        count = tien_do_importing.import_rows(rows, platform=platform, user=request.user)
    messages.success(request, f'Đã import {count} dòng tiến độ.')
    return _board_redirect(platform)


@module_perm_required(MODULE_TIEN_DO, 'create')
def import_template(request):
    response = HttpResponse(
        tien_do_importing.build_template_xlsx(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename=mau_import_tien_do.xlsx'
    return response


@require_POST
def item_cell_update(request, pk):
    """Lưu một ô inline — phân quyền theo cột (IT vs người test)."""
    item = get_object_or_404(TienDoItem, pk=pk)
    column = request.POST.get('column', '')
    value = request.POST.get('value', '')

    if column not in TienDoItem.IT_COLUMNS:
        return JsonResponse({'status': 'error', 'message': 'Cột không hợp lệ.'}, status=400)

    if not _can_edit_it_columns(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Bạn không có quyền sửa cột này.'},
            status=403,
        )

    if column in TienDoItem.RICH_COLUMNS:
        value = sanitize_actual_html(value)
    else:
        value = strip_tags(value).strip()[:255]

    setattr(item, column, value)
    item.save(update_fields=[column, 'updated_at'])
    return JsonResponse({
        'status': 'ok',
        'value': value,
        'updated_at': item.updated_at.strftime('%d/%m/%Y %H:%M'),
    })


@require_POST
def item_feedback_create(request, pk):
    """Người có quyền Sửa lưu một bản ghi Feedback + Ghi chú; người gửi = user hiện tại."""
    item = get_object_or_404(TienDoItem, pk=pk)
    if not _can_edit_tester_columns(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Bạn không có quyền ghi Feedback / Ghi chú.'},
            status=403,
        )
    feedback = sanitize_actual_html(request.POST.get('feedback', ''))
    note = sanitize_actual_html(request.POST.get('note', ''))
    if not feedback and not note:
        return JsonResponse(
            {'status': 'error', 'message': 'Nhập Feedback hoặc Ghi chú trước khi lưu.'},
            status=400,
        )
    entry = TienDoFeedback.objects.create(
        item=item, author=request.user, feedback=feedback, note=note,
    )
    TienDoItem.objects.filter(pk=item.pk).update(updated_at=timezone.now())
    return JsonResponse({
        'status': 'ok',
        'id': entry.pk,
        'author': _user_label(request.user),
        'created_at': timezone.localtime(entry.created_at).strftime('%d/%m/%Y %H:%M'),
    })


@module_perm_required(MODULE_TIEN_DO, 'delete')
@require_POST
def item_delete(request, pk):
    item = get_object_or_404(TienDoItem, pk=pk)
    platform = item.platform
    item.delete()
    messages.success(request, 'Đã xóa dòng tiến độ.')
    if platform == TienDoItem.PLATFORM_WHOLESALE_RETAIL:
        return redirect('tien_do:wholesale_retail')
    return redirect('tien_do:portal')


# --- Ảnh inline trong ô (giống ô Đánh giá thực tế của KPI) -------------------


def _upload_error(message, *, status=400):
    return JsonResponse({'uploaded': 0, 'error': {'message': message}}, status=status)


def _is_allowed_image(upload):
    content_type = (getattr(upload, 'content_type', '') or '').split(';')[0].strip().lower()
    if content_type in _IMAGE_TYPES:
        return True
    if content_type in ('', 'application/octet-stream'):
        ext = os.path.splitext(getattr(upload, 'name', '') or '')[1].lower()
        return ext in _IMAGE_EXTS or not ext
    return False


def _image_ext(upload):
    ext = os.path.splitext(upload.name or '')[1].lower()
    if ext in _IMAGE_EXTS:
        return ext
    content_type = (upload.content_type or '').split(';')[0].strip().lower()
    return _IMAGE_EXT_BY_TYPE.get(content_type, '.png')


@module_perm_required(MODULE_TIEN_DO, 'view')
@require_POST
def item_image_upload(request):
    if not (_can_edit_it_columns(request.user) or _can_edit_tester_columns(request.user)):
        return _upload_error('Bạn không có quyền chèn ảnh.', status=403)

    upload = request.FILES.get('upload') or request.FILES.get('file')
    if not upload:
        return _upload_error('Không có file.')
    if not _is_allowed_image(upload):
        return _upload_error('File không hợp lệ.')
    if upload.size > _IMAGE_MAX_BYTES:
        return _upload_error('Ảnh quá lớn (tối đa 5MB).')

    try:
        rel_path = save_inline_image(
            upload,
            username=request.user.username,
            report_date=timezone.localdate(),
            ext=_image_ext(upload),
            period=None,
        )
    except OSError as exc:
        logger.exception('Tien do image upload failed for %s: %s', request.user.username, exc)
        return _upload_error('Không lưu được ảnh. Vui lòng thử lại.', status=503)

    return JsonResponse({
        'uploaded': 1,
        'fileName': os.path.basename(rel_path),
        'url': reverse('tien_do:item_image', kwargs={'relpath': rel_path}),
    })


def _can_view_item_image(user, rel):
    """Người upload luôn xem được; người khác chỉ xem ảnh đã nằm trong một dòng tiến độ."""
    parts = rel.split('/')
    if len(parts) >= 6 and parts[2] == user.username:
        return True
    filename = parts[-1]
    if not filename:
        return False
    item_condition = Q()
    for column in TienDoItem.RICH_COLUMNS:
        item_condition |= Q(**{f'{column}__contains': filename})
    if TienDoItem.objects.filter(item_condition).exists():
        return True
    fb_condition = Q()
    for field in TienDoFeedback.RICH_FIELDS:
        fb_condition |= Q(**{f'{field}__contains': filename})
    return TienDoFeedback.objects.filter(fb_condition).exists()


@module_perm_required(MODULE_TIEN_DO, 'view')
def item_image_serve(request, relpath):
    rel = (relpath or '').lstrip('/')
    if not is_inline_image_relpath(rel):
        return HttpResponse(status=404)
    if not _can_view_item_image(request.user, rel):
        return HttpResponse(status=403)
    if not inline_image_exists(rel):
        return HttpResponse(status=404)
    content_type = mimetypes.guess_type(rel)[0] or 'application/octet-stream'
    return FileResponse(open_inline_image(rel), content_type=content_type)
