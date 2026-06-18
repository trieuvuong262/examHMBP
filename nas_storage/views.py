import os
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from hrm.module_permissions import (
    MODULE_NAS_STORAGE,
    user_can_access_module,
    user_can_create_module,
    user_can_delete_module,
)
from nas_storage.nas_paths import (
    NasPathError,
    build_breadcrumb,
    delete_nas_item,
    get_user_nas_roots,
    invalidate_listing_cache,
    list_directory_with_source,
    listing_fingerprint,
    listing_synced_at,
    nas_is_available,
    nas_path_exists,
    normalize_rel_path,
    resolve_nas_path,
    strip_legacy_dept_prefix,
    user_department_folder_code,
)
from nas_storage.share_access import (
    get_active_share,
    get_or_create_share,
    get_share_token_from_request,
    is_path_under_share,
    resolve_path_for_request,
)
from nas_storage.file_preview import (
    PREVIEWABLE_EXTENSIONS,
    inline_office_pdf_response,
    inline_pdf_response,
    share_preview_context,
)


def _access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_NAS_STORAGE):
            messages.error(request, 'Bạn không có quyền truy cập Thư mục NAS.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _rel_from_request(request) -> str:
    raw = request.GET.get('path', '')
    dept_code = user_department_folder_code(request.user)
    return strip_legacy_dept_prefix(raw, dept_code)


def _share_from_request(request):
    token = get_share_token_from_request(request)
    return get_active_share(token), token


def _attach_rel_paths(listing: dict, rel_path: str) -> None:
    for item in listing['folders']:
        item['rel_path'] = f"{rel_path}/{item['name']}"
    for item in listing['files']:
        item['rel_path'] = f"{rel_path}/{item['name']}"


def _listing_context(request, rel_path: str, *, fresh: bool = False, share=None) -> dict:
    path = resolve_path_for_request(request.user, rel_path, share=share)
    listing, source, stale = list_directory_with_source(
        path, fresh=fresh, rel_path=rel_path, user=request.user,
    )
    _attach_rel_paths(listing, rel_path)
    share_mode = share is not None
    return {
        'rel_path': rel_path,
        'breadcrumbs': build_breadcrumb(rel_path, user=request.user),
        'folders': listing['folders'],
        'files': listing['files'],
        'can_delete': (not share_mode) and user_can_delete_module(request.user, MODULE_NAS_STORAGE),
        'can_share': not share_mode,
        'share_mode': share_mode,
        'share_token': str(share.token) if share else '',
        'share_from': share.created_by if share else None,
        'share_root': share.rel_path if share else '',
        'parent_rel': '/'.join(rel_path.split('/')[:-1]) if '/' in rel_path else '',
        'synced_at': listing_synced_at(),
        'fresh_listing': fresh,
        'listing_source': source,
        'listing_stale': stale,
        'listing_key': listing_fingerprint(listing),
    }


def _browse_url(rel_path: str, *, refresh: bool = False, share_token: str = '') -> str:
    url = reverse('nas_storage:browse')
    params = {}
    if rel_path:
        params['path'] = rel_path
    if refresh:
        params['refresh'] = '1'
    if share_token:
        params['share'] = share_token
    if params:
        return f'{url}?{urlencode(params)}'
    return url


@_access_required
def browse(request):
    rel_path = _rel_from_request(request)
    fresh = request.GET.get('refresh') == '1'
    share, share_token = _share_from_request(request)
    roots = get_user_nas_roots(request.user)

    if not nas_is_available():
        return render(request, 'nas_storage/browse.html', {
            'nas_unavailable': True,
            'roots': roots,
        })

    if not roots and not share:
        return render(request, 'nas_storage/browse.html', {
            'no_department': True,
        })

    if not rel_path:
        root_entries = []
        for entry in roots:
            root_entries.append({
                'entry': entry,
                'exists': True,
            })
        from nas_storage.user_folders import user_has_custom_nas_folders

        return render(request, 'nas_storage/browse.html', {
            'root_entries': root_entries,
            'rel_path': '',
            'breadcrumbs': [{'label': 'Thư mục NAS', 'rel_path': ''}],
            'nas_using_custom': user_has_custom_nas_folders(request.user),
        })

    if share and not is_path_under_share(rel_path, share.rel_path):
        messages.error(request, 'Liên kết chia sẻ không hợp lệ cho thư mục này.')
        return redirect('nas_storage:share_open', token=share.token)

    try:
        ctx = _listing_context(request, rel_path, fresh=fresh, share=share)
    except NasPathError as exc:
        messages.error(request, str(exc))
        if share:
            return redirect('nas_storage:share_open', token=share.token)
        return redirect('nas_storage:browse')
    except FileNotFoundError:
        messages.error(request, 'Thư mục không tồn tại trên NAS.')
        if share:
            return redirect('nas_storage:share_open', token=share.token)
        return redirect('nas_storage:browse')

    if fresh:
        if ctx.get('listing_source') == 'rclone':
            messages.success(request, f'Đã đồng bộ lúc {ctx["synced_at"]} (trực tiếp từ NAS).')
        elif ctx.get('listing_stale'):
            messages.warning(
                request,
                'Chưa đồng bộ trực tiếp từ NAS — danh sách có thể cũ. Liên hệ IT kiểm tra rclone.',
            )

    return render(request, 'nas_storage/browse.html', ctx)


@login_required
def open_share(request, token):
    if not user_can_access_module(request.user, MODULE_NAS_STORAGE):
        messages.error(request, 'Bạn cần quyền Thư mục NAS trên Portal để mở liên kết chia sẻ.')
        return redirect('home_portal')

    share = get_active_share(str(token))
    if not share:
        messages.error(request, 'Liên kết chia sẻ không tồn tại hoặc đã bị vô hiệu.')
        return redirect('nas_storage:browse')

    share_token = str(share.token)
    try:
        path = resolve_path_for_request(request.user, share.rel_path, share=share)
    except NasPathError as exc:
        messages.error(request, str(exc))
        return redirect('nas_storage:browse')

    if share.is_dir and path.is_dir():
        return redirect(_browse_url(share.rel_path, share_token=share_token))

    if path.is_file():
        file_preview = share_preview_context(share.item_name, share.rel_path, share_token=share_token)
        return render(request, 'nas_storage/share_open.html', {
            'share': share,
            'share_token': share_token,
            'file_name': share.item_name,
            'file_size': path.stat().st_size,
            'file_preview': file_preview,
            'download_url': (
                reverse('nas_storage:download')
                + '?'
                + urlencode({'path': share.rel_path, 'share': share_token})
            ),
        })

    messages.error(request, 'File hoặc thư mục không còn tồn tại trên NAS.')
    return redirect('nas_storage:browse')


@_access_required
@require_POST
def create_share(request):
    if not user_can_create_module(request.user, MODULE_NAS_STORAGE):
        return JsonResponse({'error': 'Bạn không có quyền tạo link chia sẻ.'}, status=403)

    rel_path = normalize_rel_path(request.POST.get('path', ''))
    if not rel_path:
        return JsonResponse({'error': 'missing path'}, status=400)

    try:
        path = resolve_nas_path(request.user, rel_path)
    except NasPathError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    if not path.exists():
        return JsonResponse({'error': 'Không tìm thấy trên NAS.'}, status=404)

    share = get_or_create_share(
        request.user,
        rel_path,
        item_name=path.name,
        is_dir=path.is_dir(),
    )
    share_url = request.build_absolute_uri(
        reverse('nas_storage:share_open', args=[share.token])
    )
    return JsonResponse({
        'url': share_url,
        'token': str(share.token),
        'item_name': share.item_name,
        'is_dir': share.is_dir,
    })


@login_required
def preview_file(request):
    if not user_can_access_module(request.user, MODULE_NAS_STORAGE):
        messages.error(request, 'Bạn cần quyền Thư mục NAS trên Portal để xem trước file.')
        return redirect('home_portal')

    rel_path = _rel_from_request(request)
    share, share_token = _share_from_request(request)
    if not rel_path:
        raise Http404

    if share and not is_path_under_share(rel_path, share.rel_path):
        raise Http404

    try:
        path = resolve_path_for_request(request.user, rel_path, share=share)
    except NasPathError as exc:
        messages.error(request, str(exc))
        if share:
            return redirect('nas_storage:share_open', token=share.token)
        return redirect('nas_storage:browse')

    if not path.is_file():
        raise Http404

    ext = path.suffix.lower()
    if ext not in PREVIEWABLE_EXTENSIONS:
        raise Http404

    try:
        if ext == '.pdf':
            return inline_pdf_response(path)
        return inline_office_pdf_response(path, display_name=path.name)
    except ValidationError as exc:
        messages.error(request, str(exc))
        if share:
            return redirect('nas_storage:share_open', token=share.token)
        return redirect(_browse_url(rel_path, share_token=share_token))


@_access_required
def download(request):
    rel_path = _rel_from_request(request)
    share, share_token = _share_from_request(request)
    if not rel_path:
        raise Http404

    if share and not is_path_under_share(rel_path, share.rel_path):
        raise Http404

    try:
        path = resolve_path_for_request(request.user, rel_path, share=share)
    except NasPathError as exc:
        messages.error(request, str(exc))
        if share:
            return redirect('nas_storage:share_open', token=share.token)
        return redirect('nas_storage:browse')

    if not path.is_file():
        raise Http404

    parent = os.path.dirname(rel_path)
    response = FileResponse(path.open('rb'), as_attachment=True, filename=path.name)
    response['Content-Length'] = path.stat().st_size
    if parent:
        response['X-NAS-Parent'] = parent
    return response


@_access_required
@require_POST
def delete_entry(request):
    if not user_can_delete_module(request.user, MODULE_NAS_STORAGE):
        messages.error(request, 'Bạn không có quyền xóa.')
        return redirect('nas_storage:browse')

    dept_code = user_department_folder_code(request.user)
    rel_path = strip_legacy_dept_prefix(request.POST.get('path', ''), dept_code)
    parent_rel = strip_legacy_dept_prefix(request.POST.get('parent', ''), dept_code)

    if not rel_path:
        messages.error(request, 'Chưa chọn mục cần xóa.')
        return redirect(_browse_url(parent_rel))

    try:
        resolve_nas_path(request.user, rel_path)
    except NasPathError as exc:
        messages.error(request, str(exc))
        return redirect(_browse_url(parent_rel))

    try:
        name = delete_nas_item(request.user, rel_path)
    except NasPathError as exc:
        messages.error(request, str(exc))
        return redirect(_browse_url(parent_rel or rel_path))

    invalidate_listing_cache(request.user, parent_rel or rel_path)
    messages.success(request, f'Đã xóa "{name}".')
    return redirect(_browse_url(parent_rel, refresh=True))
