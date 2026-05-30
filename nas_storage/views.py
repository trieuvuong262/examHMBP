import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from hrm.module_permissions import (
    MODULE_NAS_STORAGE,
    user_can_access_module,
    user_can_create_module,
    user_can_delete_module,
)
from nas_storage.nas_paths import (
    NasPathError,
    build_breadcrumb,
    get_user_nas_roots,
    list_directory,
    nas_is_available,
    normalize_rel_path,
    resolve_nas_path,
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
    return normalize_rel_path(request.GET.get('path', ''))


@_access_required
def browse(request):
    rel_path = _rel_from_request(request)
    roots = get_user_nas_roots(request.user)

    if not nas_is_available():
        return render(request, 'nas_storage/browse.html', {
            'nas_unavailable': True,
            'roots': roots,
        })

    if not roots:
        return render(request, 'nas_storage/browse.html', {
            'no_department': True,
        })

    if not rel_path:
        root_entries = []
        for entry in roots:
            try:
                path = resolve_nas_path(request.user, entry.rel_path)
                exists = path.is_dir()
            except NasPathError:
                exists = False
            root_entries.append({
                'entry': entry,
                'exists': exists,
            })
        return render(request, 'nas_storage/browse.html', {
            'root_entries': root_entries,
            'rel_path': '',
            'breadcrumbs': [{'label': 'Thư mục NAS', 'rel_path': ''}],
        })

    try:
        path = resolve_nas_path(request.user, rel_path)
        listing = list_directory(path)
    except NasPathError as exc:
        messages.error(request, str(exc))
        return redirect('nas_storage:browse')
    except FileNotFoundError:
        messages.error(request, 'Thư mục không tồn tại trên NAS.')
        return redirect('nas_storage:browse')

    for item in listing['folders']:
        item['rel_path'] = f"{rel_path}/{item['name']}"
    for item in listing['files']:
        item['rel_path'] = f"{rel_path}/{item['name']}"

    return render(request, 'nas_storage/browse.html', {
        'rel_path': rel_path,
        'breadcrumbs': build_breadcrumb(rel_path),
        'folders': listing['folders'],
        'files': listing['files'],
        'can_upload': user_can_create_module(request.user, MODULE_NAS_STORAGE),
        'can_delete': user_can_delete_module(request.user, MODULE_NAS_STORAGE),
        'parent_rel': '/'.join(rel_path.split('/')[:-1]) if '/' in rel_path else '',
    })


@_access_required
def download(request):
    rel_path = _rel_from_request(request)
    if not rel_path:
        raise Http404

    try:
        path = resolve_nas_path(request.user, rel_path)
    except NasPathError as exc:
        messages.error(request, str(exc))
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
def upload(request):
    if not user_can_create_module(request.user, MODULE_NAS_STORAGE):
        messages.error(request, 'Bạn không có quyền tải lên file.')
        return redirect('nas_storage:browse')

    rel_dir = normalize_rel_path(request.POST.get('path', ''))
    if not rel_dir:
        messages.error(request, 'Chọn thư mục đích trước khi tải lên.')
        return redirect('nas_storage:browse')

    try:
        dir_path = resolve_nas_path(request.user, rel_dir)
    except NasPathError as exc:
        messages.error(request, str(exc))
        return redirect('nas_storage:browse')

    if not dir_path.is_dir():
        messages.error(request, 'Thư mục đích không tồn tại.')
        return redirect('nas_storage:browse', **{})

    uploaded = request.FILES.get('file')
    if not uploaded:
        messages.error(request, 'Chưa chọn file.')
        return redirect(_browse_url(rel_dir))

    filename = os.path.basename(uploaded.name)
    if not filename or filename.startswith('.') or '/' in filename or '\\' in filename:
        messages.error(request, 'Tên file không hợp lệ.')
        return redirect(_browse_url(rel_dir))

    dest = dir_path / filename
    if dest.exists():
        messages.error(request, f'File "{filename}" đã tồn tại.')
        return redirect(_browse_url(rel_dir))

    with dest.open('wb') as out:
        for chunk in uploaded.chunks():
            out.write(chunk)

    messages.success(request, f'Đã tải lên "{filename}".')
    return redirect(_browse_url(rel_dir))


@_access_required
@require_POST
def delete_entry(request):
    if not user_can_delete_module(request.user, MODULE_NAS_STORAGE):
        messages.error(request, 'Bạn không có quyền xóa.')
        return redirect('nas_storage:browse')

    rel_path = normalize_rel_path(request.POST.get('path', ''))
    parent_rel = normalize_rel_path(request.POST.get('parent', ''))

    try:
        path = resolve_nas_path(request.user, rel_path)
    except NasPathError as exc:
        messages.error(request, str(exc))
        return redirect('nas_storage:browse')

    name = path.name
    if path.is_dir():
        if any(path.iterdir()):
            messages.error(request, 'Chỉ xóa được thư mục rỗng.')
            return redirect(_browse_url(parent_rel or rel_path))
        path.rmdir()
    elif path.is_file():
        path.unlink()
    else:
        messages.error(request, 'Không tìm thấy file hoặc thư mục.')
        return redirect(_browse_url(parent_rel))

    messages.success(request, f'Đã xóa "{name}".')
    return redirect(_browse_url(parent_rel))


def _browse_url(rel_path: str) -> str:
    from django.urls import reverse
    url = reverse('nas_storage:browse')
    if rel_path:
        return f'{url}?path={rel_path}'
    return url
